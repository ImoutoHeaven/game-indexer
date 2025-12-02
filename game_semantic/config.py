"""Configuration helpers for BGE-M3 + Meilisearch tools."""

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, Optional


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    """Convert an environment string to a bool, returning None when ambiguous."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    """Convert an environment string to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass
class Config:
    """Container for all runtime settings."""

    meili_url: str = "http://127.0.0.1:7700"
    meili_api_key: str = "masterKey"
    meili_index_uid: str = "games"
    mode: str = "rebuild"  # rebuild | append | refine
    bge_model_name: str = "BAAI/bge-m3"
    bge_use_fp16: bool = False
    encode_batch_size: int = 64
    index_batch_size: int = 256
    top_k: int = 10
    txt_path: str = "games.txt"
    debug: bool = False


def load_config_from_env_and_args(args: object, config_path: Optional[str] = None) -> Config:
    """
    Merge CLI args + env + config.json (if present) into a Config instance.

    Priority: CLI > environment > config.json > defaults.
    """

    def load_file(path: str = "config.json") -> Dict[str, object]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                return json.load(fp) or {}
        except Exception:
            return {}

    def pick(cli_val, env_val, default):
        if cli_val is not None:
            return cli_val
        if env_val is not None:
            return env_val
        return default

    file_cfg = load_file(config_path or "config.json")

    env_meili_url = os.getenv("MEILI_URL", file_cfg.get("meili_url"))
    env_meili_api_key = os.getenv("MEILI_API_KEY", file_cfg.get("meili_api_key"))
    env_meili_index_uid = os.getenv("MEILI_INDEX_UID", file_cfg.get("meili_index_uid"))
    env_mode = os.getenv("MODE", file_cfg.get("mode"))
    env_bge_model_name = os.getenv("BGE_MODEL_NAME", file_cfg.get("bge_model_name"))
    env_bge_use_fp16 = _parse_bool(os.getenv("BGE_USE_FP16")) if os.getenv("BGE_USE_FP16") is not None else _parse_bool(str(file_cfg.get("bge_use_fp16")) if file_cfg.get("bge_use_fp16") is not None else None)
    env_encode_batch_size = _parse_int(os.getenv("ENCODE_BATCH_SIZE")) if os.getenv("ENCODE_BATCH_SIZE") is not None else _parse_int(str(file_cfg.get("encode_batch_size")) if file_cfg.get("encode_batch_size") is not None else None)
    env_index_batch_size = _parse_int(os.getenv("INDEX_BATCH_SIZE")) if os.getenv("INDEX_BATCH_SIZE") is not None else _parse_int(str(file_cfg.get("index_batch_size")) if file_cfg.get("index_batch_size") is not None else None)
    env_top_k = _parse_int(os.getenv("TOP_K")) if os.getenv("TOP_K") is not None else _parse_int(str(file_cfg.get("top_k")) if file_cfg.get("top_k") is not None else None)
    env_txt_path = os.getenv("TXT_PATH", file_cfg.get("txt_path"))
    env_debug = _parse_bool(os.getenv("DEBUG")) if os.getenv("DEBUG") is not None else _parse_bool(str(file_cfg.get("debug")) if file_cfg.get("debug") is not None else None)

    meili_url = pick(getattr(args, "meili_url", None), env_meili_url, Config.meili_url)
    meili_api_key = pick(getattr(args, "meili_api_key", None), env_meili_api_key, Config.meili_api_key)
    meili_index_uid = pick(getattr(args, "meili_index_uid", None), env_meili_index_uid, Config.meili_index_uid)
    mode = pick(getattr(args, "mode", None), env_mode, Config.mode)
    bge_model_name = pick(getattr(args, "bge_model_name", None), env_bge_model_name, Config.bge_model_name)
    bge_use_fp16 = pick(getattr(args, "bge_use_fp16", None), env_bge_use_fp16, Config.bge_use_fp16)
    encode_batch_size = pick(getattr(args, "encode_batch_size", None), env_encode_batch_size, Config.encode_batch_size)
    index_batch_size = pick(getattr(args, "index_batch_size", None), env_index_batch_size, Config.index_batch_size)
    top_k = pick(getattr(args, "top_k", None), env_top_k, Config.top_k)
    txt_path = pick(getattr(args, "txt_path", None), env_txt_path, Config.txt_path)
    debug = pick(getattr(args, "debug", None), env_debug, Config.debug)

    return Config(
        meili_url=meili_url,
        meili_api_key=meili_api_key,
        meili_index_uid=meili_index_uid,
        mode=mode,
        bge_model_name=bge_model_name,
        bge_use_fp16=bool(bge_use_fp16),
        encode_batch_size=int(encode_batch_size),
        index_batch_size=int(index_batch_size),
        top_k=int(top_k),
        txt_path=txt_path,
        debug=bool(debug),
    )


def export_config(config: Config, path: str = "config.json"):
    """
    Persist key settings (especially Meilisearch connection) to a JSON file.
    """
    data = asdict(config)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
