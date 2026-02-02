#!/usr/bin/env python3
"""CLI entrypoint for interactive semantic search."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_semantic.config import load_config_from_env_and_args
from game_semantic import service


def main():
    parser = argparse.ArgumentParser(description="Search games via BGE-M3 + Meilisearch.")
    parser.add_argument("--meili-url", dest="meili_url", help="Meilisearch endpoint URL.")
    parser.add_argument("--meili-api-key", dest="meili_api_key", help="Meilisearch API key.")
    parser.add_argument("--index-uid", dest="meili_index_uid", help="Index UID to use.")
    parser.add_argument("--top-k", dest="top_k", type=int, help="Number of results to return.")
    parser.add_argument("--bge-model-name", dest="bge_model_name", help="Model name to load.")
    parser.set_defaults(bge_use_fp16=None)
    parser.add_argument("--bge-use-fp16", dest="bge_use_fp16", action="store_true", help="Force FP16.")
    parser.add_argument("--bge-use-fp32", dest="bge_use_fp16", action="store_false", help="Force FP32/FP16 off.")
    parser.add_argument("--debug", dest="debug", action="store_true", default=None, help="Enable debug logging.")

    args = parser.parse_args()
    config = load_config_from_env_and_args(args)
    service.search_games(config)


if __name__ == "__main__":
    main()
