#!/usr/bin/env python3
"""CLI entrypoint to build the Meilisearch games index."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_semantic.config import load_config_from_env_and_args
from game_semantic import service


def main():
    parser = argparse.ArgumentParser(description="Build BGE-M3 vectors into a Meilisearch index.")
    parser.add_argument("-c", "--config", dest="config_path", help="Path to config.json (defaults to ./config.json).")
    parser.add_argument("--meili-url", dest="meili_url", help="Meilisearch endpoint URL.")
    parser.add_argument("--meili-api-key", dest="meili_api_key", help="Meilisearch API key.")
    parser.add_argument("--index-uid", dest="meili_index_uid", help="Index UID to use.")
    parser.add_argument(
        "--mode",
        dest="mode",
        choices=["rebuild", "append", "refine"],
        help="Index mode: rebuild (default), append (add new names), refine (pull existing index, dedup, drop, rebuild).",
    )
    parser.add_argument("--txt-path", dest="txt_path", help="Path to games.txt.")
    parser.add_argument("--bge-model-name", dest="bge_model_name", help="Model name to load.")
    parser.set_defaults(bge_use_fp16=None)
    parser.add_argument("--bge-use-fp16", dest="bge_use_fp16", action="store_true", help="Force FP16.")
    parser.add_argument("--bge-use-fp32", dest="bge_use_fp16", action="store_false", help="Force FP32/FP16 off.")
    parser.add_argument("--encode-batch-size", dest="encode_batch_size", type=int, help="Batch size for embedding.")
    parser.add_argument("--index-batch-size", dest="index_batch_size", type=int, help="Batch size for index writes.")
    parser.add_argument("--debug", dest="debug", action="store_true", default=None, help="Enable debug logging.")

    args = parser.parse_args()
    config = load_config_from_env_and_args(args, config_path=args.config_path)
    service.build_index(config)


if __name__ == "__main__":
    main()
