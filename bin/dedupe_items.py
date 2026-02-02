#!/usr/bin/env python3
"""Generic similarity dedupe CLI for txt/json or directory scans via BGE-M3 + Meilisearch."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_semantic.config import load_config_from_env_and_args
from game_semantic.deduper import (
    dump_items_to_json,
    load_items_from_json,
    load_items_from_txt,
    scan_filesystem,
)
from game_semantic import service


def main():
    parser = argparse.ArgumentParser(
        description="Group near-duplicate filenames/items by similarity threshold."
    )
    parser.add_argument("-i", "--input", dest="input_path", help="Input file path (txt or json).")
    parser.add_argument("--fs", dest="fs_path", help="Recursively scan a directory as input.")
    parser.add_argument(
        "--output-json", dest="output_json", help="When using --fs, save scan output to JSON."
    )
    parser.add_argument(
        "--mode",
        dest="mode",
        choices=["rebuild", "append"],
        help="Index mode: rebuild or append.",
    )
    parser.add_argument(
        "--threshold", dest="threshold", type=float, default=0.85, help="Composite similarity threshold."
    )
    parser.add_argument("--top-k", dest="top_k", type=int, help="Nearest neighbors per item.")
    parser.add_argument(
        "--time-window", dest="time_window", type=float, default=900.0, help="Time similarity window (seconds)."
    )
    parser.add_argument(
        "--check-time",
        dest="check_time",
        action="store_true",
        help="Use both ctime and mtime for similarity.",
    )
    parser.add_argument("--check-ctime", dest="check_ctime", action="store_true", help="Use ctime for similarity.")
    parser.add_argument("--check-mtime", dest="check_mtime", action="store_true", help="Use mtime for similarity.")
    parser.add_argument("--check-size", dest="check_size", action="store_true", help="Use file size for similarity.")

    parser.add_argument("--meili-url", dest="meili_url", help="Meilisearch endpoint URL.")
    parser.add_argument("--meili-api-key", dest="meili_api_key", help="Meilisearch API key.")
    parser.add_argument("--index-uid", dest="meili_index_uid", help="Index UID to use.")
    parser.add_argument("--bge-model-name", dest="bge_model_name", help="Model name to load.")
    parser.set_defaults(bge_use_fp16=None)
    parser.add_argument("--bge-use-fp16", dest="bge_use_fp16", action="store_true", help="Force FP16.")
    parser.add_argument("--bge-use-fp32", dest="bge_use_fp16", action="store_false", help="Force FP32/FP16 off.")
    parser.add_argument("--encode-batch-size", dest="encode_batch_size", type=int, help="Batch size for embedding.")
    parser.add_argument("--index-batch-size", dest="index_batch_size", type=int, help="Batch size for index writes.")
    parser.add_argument("--debug", dest="debug", action="store_true", default=None, help="Enable debug logging.")

    args = parser.parse_args()
    if args.input_path and args.fs_path:
        parser.error("Cannot specify both --input and --fs.")

    config = load_config_from_env_and_args(args)

    items = []
    if args.fs_path:
        items = scan_filesystem(args.fs_path)
        output_path = args.output_json or "fs_scan.json"
        dump_items_to_json(items, output_path)
        print(f"Wrote scan output to {output_path}")
    else:
        input_path = args.input_path or config.txt_path
        if not input_path:
            parser.error("Provide --input or --fs.")
        suffix = Path(input_path).suffix.lower()
        if suffix == ".json":
            items = load_items_from_json(input_path)
        else:
            items = load_items_from_txt(input_path)

    if not items:
        print("No records to process.")
        return

    check_ctime = bool(args.check_ctime or args.check_time)
    check_mtime = bool(args.check_mtime or args.check_time)

    service.dedupe_items(
        items,
        config=config,
        mode=args.mode or config.mode,
        threshold=args.threshold,
        top_k=args.top_k,
        check_ctime=check_ctime,
        check_mtime=check_mtime,
        check_size=bool(args.check_size),
        time_window=args.time_window,
    )


if __name__ == "__main__":
    main()
