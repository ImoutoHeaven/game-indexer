"""Interactive CLI for semantic game search."""

import logging
import sys

from .config import Config
from .embedding import BgeM3Embedder
from .meili_client import MeiliGameIndex


def interactive_search(config: Config):
    """Run a simple REPL that embeds user queries and searches Meilisearch."""
    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    print("初始化中：连接 Meilisearch 并加载 BGE-M3 模型（首次运行会下载模型，可能需 1-3 分钟）...", flush=True)
    try:
        game_index = MeiliGameIndex(
            url=config.meili_url,
            api_key=config.meili_api_key,
            index_uid=config.meili_index_uid,
            embedder_name="bge_m3",
            embedding_dim=1024,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"无法连接 Meilisearch：{exc}", file=sys.stderr)
        return

    try:
        embedder = BgeM3Embedder(model_name=config.bge_model_name, use_fp16=config.bge_use_fp16)
    except Exception as exc:  # noqa: BLE001
        print(f"加载 BGE-M3 模型失败：{exc}", file=sys.stderr)
        return

    def highlight(text: str, query: str) -> str:
        """Highlight exact query substring in red if present."""
        if not query or not text:
            return text
        return text.replace(query, f"\033[31m{query}\033[0m")

    print("输入查询（任意语言），按 Enter 进行向量搜索；直接回车退出。")

    while True:
        try:
            query = input("请输入查询> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见～")
            break

        if not query:
            print("空行，退出。")
            break

        logging.debug("User query: %s", query)
        dense = embedder.encode_dense([query], batch_size=1, max_length=128)
        query_vec = dense[0].tolist()
        logging.debug("Encoded query vector dim=%d", len(query_vec))

        hits = game_index.search_by_vector(query_vec, limit=config.top_k)
        logging.debug("Search returned %d hits", len(hits))

        if not hits:
            print("（没有找到相似的游戏）\n")
            continue

        print(f"Top {len(hits)} 相似结果：")
        for idx, doc in enumerate(hits, 1):
            name = doc.get("name", "")
            print(f"{idx}. {highlight(name, query)}")
        print("")
