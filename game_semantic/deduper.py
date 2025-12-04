"""相似度阈值去重与近似分组工具（BGE-M3 + Meilisearch）。"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .config import Config
from .embedding import BgeM3Embedder
from .meili_client import MeiliGameIndex


@dataclass
class ItemRecord:
    """载入的文件或名称记录。"""

    name: str
    path: Optional[str] = None
    ctime: Optional[float] = None
    mtime: Optional[float] = None
    size: Optional[int] = None
    source: str = "new"  # new | existing


def _deduplicate_preserve_order(items: List[ItemRecord]) -> List[ItemRecord]:
    """按名称去重并保持顺序。"""
    seen: Set[str] = set()
    output: List[ItemRecord] = []
    for item in items:
        if not item.name or item.name in seen:
            continue
        seen.add(item.name)
        output.append(item)
    return output


def load_items_from_txt(path: str) -> List[ItemRecord]:
    """从 txt 文件读取名称列表。"""
    records: List[ItemRecord] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            name = line.strip()
            if name:
                records.append(ItemRecord(name=name))
    return records


def load_items_from_json(path: str) -> List[ItemRecord]:
    """读取 JSON 列表格式的记录。"""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        logging.warning("JSON 数据不是列表，忽略。")
        return []
    records: List[ItemRecord] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("filename")
        if not name:
            continue
        records.append(
            ItemRecord(
                name=str(name),
                path=entry.get("path"),
                ctime=entry.get("ctime"),
                mtime=entry.get("mtime"),
                size=entry.get("size"),
            )
        )
    return records


def scan_filesystem(fs_root: str) -> List[ItemRecord]:
    """递归扫描文件系统，采集文件名及时间、大小。"""
    root = Path(fs_root)
    if not root.exists():
        logging.warning("路径不存在：%s", fs_root)
        return []
    records: List[ItemRecord] = []
    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except Exception as exc:  # noqa: BLE001
            logging.debug("无法读取 %s: %s", path, exc)
            continue
        records.append(
            ItemRecord(
                name=path.name,
                path=str(path),
                ctime=stat.st_ctime,
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
        )
    return records


def dump_items_to_json(items: List[ItemRecord], output_path: str):
    """将记录写入 JSON。"""
    serializable = []
    for item in items:
        serializable.append(
            {
                "name": item.name,
                "path": item.path,
                "ctime": item.ctime,
                "mtime": item.mtime,
                "size": item.size,
            }
        )
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(serializable, handle, ensure_ascii=False, indent=2)


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if denom == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denom)


def _time_similarity(a: Optional[float], b: Optional[float], window_seconds: float) -> Optional[float]:
    if a is None or b is None:
        return None
    diff = abs(a - b)
    return max(0.0, 1.0 - diff / max(window_seconds, 1.0))


def _size_similarity(a: Optional[int], b: Optional[int]) -> Optional[float]:
    if a is None or b is None:
        return None
    max_size = max(a, b, 1)
    diff_ratio = abs(a - b) / max_size
    return max(0.0, 1.0 - min(diff_ratio, 1.0))


def _combined_similarity(
    name_sim: float,
    meta_sims: Dict[str, float],
) -> float:
    if not meta_sims:
        return name_sim
    return (name_sim + sum(meta_sims.values())) / (1.0 + len(meta_sims))


def _union_find(parents: Dict[int, int], node: int) -> int:
    parents.setdefault(node, node)
    if parents[node] != node:
        parents[node] = _union_find(parents, parents[node])
    return parents[node]


def _union(parents: Dict[int, int], a: int, b: int):
    ra, rb = _union_find(parents, a), _union_find(parents, b)
    if ra != rb:
        parents[rb] = ra


def _create_index(config: Config, displayed_attributes: List[str]) -> MeiliGameIndex:
    return MeiliGameIndex(
        url=config.meili_url,
        api_key=config.meili_api_key,
        index_uid=config.meili_index_uid,
        embedder_name="bge_m3",
        embedding_dim=1024,
        displayed_attributes=displayed_attributes,
    )


def dedupe_items(
    items: List[ItemRecord],
    config: Config,
    mode: str = "rebuild",
    threshold: float = 0.85,
    top_k: Optional[int] = None,
    check_ctime: bool = False,
    check_mtime: bool = False,
    check_size: bool = False,
    time_window: float = 900.0,
):
    """主入口：索引并按阈值分组相似名称。"""
    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
    start_time = time.time()

    items = _deduplicate_preserve_order(items)
    if not items:
        logging.info("没有可处理的记录。")
        return

    mode = (mode or "rebuild").lower()
    if mode not in {"rebuild", "append"}:
        logging.warning("未知模式 %s，默认为 rebuild。", mode)
        mode = "rebuild"

    displayed_attributes = ["id", "name", "path", "ctime", "mtime", "size"]
    game_index = _create_index(config, displayed_attributes=displayed_attributes)

    if mode == "rebuild":
        game_index.delete_index()
        game_index = _create_index(config, displayed_attributes=displayed_attributes)

    game_index.ensure_settings()

    existing_names: Set[str] = set()
    start_id = 1
    if mode == "append":
        existing_names, max_id = game_index.fetch_existing_names_and_max_id()
        start_id = max_id + 1
        before_filter = len(items)
        items = [item for item in items if item.name not in existing_names]
        logging.info("Append 模式：过滤掉 %d 个已存在名称，剩余 %d 个新名称。", before_filter - len(items), len(items))
        if not items:
            logging.info("没有新名称需要追加，结束。")
            return

    embedder = BgeM3Embedder(model_name=config.bge_model_name, use_fp16=config.bge_use_fp16)
    names = [item.name for item in items]
    dense_vecs = embedder.encode_dense(
        names,
        batch_size=min(config.encode_batch_size, len(names)),
        max_length=128,
    )

    id_to_item: Dict[int, ItemRecord] = {}
    id_to_vector: Dict[int, np.ndarray] = {}
    docs_batch: List[dict] = []
    next_id = start_id

    for item, vec in zip(items, dense_vecs):
        item_id = next_id
        next_id += 1
        id_to_item[item_id] = item
        id_to_vector[item_id] = vec
        doc = {
            "id": item_id,
            "name": item.name,
            "path": item.path,
            "ctime": item.ctime,
            "mtime": item.mtime,
            "size": item.size,
            "_vectors": {"bge_m3": vec.tolist()},
        }
        docs_batch.append(doc)
        if len(docs_batch) >= config.index_batch_size:
            logging.info("写入 %d 条记录到 Meilisearch（当前 id < %d）。", len(docs_batch), item_id + 1)
            game_index.add_documents(docs_batch, wait=True)
            docs_batch = []

    if docs_batch:
        logging.info("写入最后 %d 条记录到 Meilisearch。", len(docs_batch))
        game_index.add_documents(docs_batch, wait=True)

    # 相似度检查
    neighbor_limit = top_k or config.top_k
    pair_keys: Set[Tuple[int, int]] = set()
    parents: Dict[int, int] = {}
    edges: List[Tuple[int, int, float, float, Dict[str, float]]] = []
    name_vec_cache: Dict[str, np.ndarray] = {}

    def vector_for_name(name: str) -> np.ndarray:
        if name in name_vec_cache:
            return name_vec_cache[name]
        encoded = embedder.encode_dense([name], batch_size=1, max_length=128)
        name_vec_cache[name] = encoded[0]
        return encoded[0]

    def compute_meta_sims(a: ItemRecord, b: ItemRecord) -> Dict[str, float]:
        meta: Dict[str, float] = {}
        if check_ctime:
            sim = _time_similarity(a.ctime, b.ctime, time_window)
            if sim is not None:
                meta["ctime"] = sim
        if check_mtime:
            sim = _time_similarity(a.mtime, b.mtime, time_window)
            if sim is not None:
                meta["mtime"] = sim
        if check_size:
            sim = _size_similarity(a.size, b.size)
            if sim is not None:
                meta["size"] = sim
        return meta

    logging.info("开始相似度检索，阈值=%.3f，邻居数量=%d。", threshold, neighbor_limit)
    for item_id, vec in id_to_vector.items():
        hits = game_index.search_by_vector(vec.tolist(), limit=neighbor_limit)
        for hit in hits:
            hit_id = hit.get("id")
            if not isinstance(hit_id, int) or hit_id == item_id:
                continue
            key = tuple(sorted((item_id, hit_id)))
            if key in pair_keys:
                continue
            pair_keys.add(key)

            hit_item = id_to_item.get(hit_id)
            if hit_item is None:
                hit_item = ItemRecord(
                    name=hit.get("name", ""),
                    path=hit.get("path"),
                    ctime=hit.get("ctime"),
                    mtime=hit.get("mtime"),
                    size=hit.get("size"),
                    source="existing",
                )
                id_to_item[hit_id] = hit_item
            other_vec = id_to_vector.get(hit_id)
            if other_vec is None:
                other_vec = vector_for_name(hit_item.name)
                id_to_vector[hit_id] = other_vec

            name_sim = _cosine_similarity(vec, other_vec)
            meta_sims = compute_meta_sims(id_to_item[item_id], hit_item)
            combined = _combined_similarity(name_sim, meta_sims)

            if combined < threshold:
                continue

            _union(parents, item_id, hit_id)
            edges.append((item_id, hit_id, combined, name_sim, meta_sims))

    if not edges:
        logging.info("未发现高相似度分组。耗时 %.2fs", time.time() - start_time)
        return

    groups: Dict[int, Set[int]] = {}
    for node_a, node_b, _, _, _ in edges:
        root = _union_find(parents, node_a)
        groups.setdefault(root, set()).update({node_a, node_b})

    logging.info("共发现 %d 个高相似度分组。", len(groups))
    group_num = 1
    for root, members in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        print(f"\n[分组 {group_num}] 共 {len(members)} 个条目：")
        group_edges = [edge for edge in edges if _union_find(parents, edge[0]) == root]
        member_list = sorted(members)
        for mid in member_list:
            rec = id_to_item.get(mid)
            meta_desc = []
            if rec.size is not None:
                meta_desc.append(f"size={rec.size}")
            if rec.ctime is not None:
                meta_desc.append(f"ctime={rec.ctime:.0f}")
            if rec.mtime is not None:
                meta_desc.append(f"mtime={rec.mtime:.0f}")
            meta_str = "; ".join(meta_desc)
            source = getattr(rec, "source", "new")
            print(f"  - id={mid} [{source}] {rec.name} ({meta_str})")

        for edge in sorted(group_edges, key=lambda e: e[2], reverse=True):
            a, b, combined, name_sim, meta_sims = edge
            meta_parts = [f"{k}={v:.3f}" for k, v in meta_sims.items()]
            meta_part = "; ".join(meta_parts)
            print(
                f"    * 相似对 id {a} <-> {b}: 综合={combined:.3f}, 名称={name_sim:.3f}"
                + (f", 其他={meta_part}" if meta_part else "")
            )
        group_num += 1

    elapsed = time.time() - start_time
    logging.info("去重检查完成，耗时 %.2fs", elapsed)
