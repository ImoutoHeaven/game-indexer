"""Build the Meilisearch index from a plain-text games list."""

import logging
import time
from typing import List

from .config import Config
from .embedding import BgeM3Embedder
from .meili_client import MeiliGameIndex

VALID_MODES = {"rebuild", "append", "refine"}


def load_game_names(txt_path: str) -> List[str]:
    """
    Read non-empty lines from the given text file.

    Leading/trailing whitespace is stripped; empty lines are ignored.
    """
    names: List[str] = []
    with open(txt_path, "r", encoding="utf-8") as handle:
        for line in handle:
            name = line.strip()
            if name:
                names.append(name)
    return names


def _deduplicate_preserve_order(items: List[str]) -> List[str]:
    """Remove duplicates while preserving order."""
    seen = set()
    output = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def build_index(config: Config):
    """Load names, embed them, and push to Meilisearch."""
    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
    start_time = time.time()

    mode = (config.mode or "rebuild").lower()
    if mode not in VALID_MODES:
        logging.warning("Unknown mode '%s', defaulting to 'rebuild'", mode)
        mode = "rebuild"

    game_index = MeiliGameIndex(
        url=config.meili_url,
        api_key=config.meili_api_key,
        index_uid=config.meili_index_uid,
        embedder_name="bge_m3",
        embedding_dim=1024,
    )

    if mode == "refine":
        logging.info("Mode=refine: fetching all existing names for dedup + rebuild.")
        names = game_index.fetch_all_names_list()
        names = _deduplicate_preserve_order(names)
        logging.info("Refine: fetched %d names after dedup", len(names))
        if not names:
            logging.warning("No names found in index; nothing to refine.")
            return
        logging.info("Deleting index %s before refining", config.meili_index_uid)
        game_index.delete_index()
        game_index = MeiliGameIndex(
            url=config.meili_url,
            api_key=config.meili_api_key,
            index_uid=config.meili_index_uid,
            embedder_name="bge_m3",
            embedding_dim=1024,
        )
    else:
        names = load_game_names(config.txt_path)
        names = _deduplicate_preserve_order(names)
        logging.info("Loaded %d game names from %s (deduplicated)", len(names), config.txt_path)
        logging.debug("Sample names: %s", names[:3] if names else [])
        if not names:
            logging.warning("No names to index; aborting.")
            return

        if mode == "rebuild":
            logging.info("Mode=rebuild: deleting target index %s before rebuild", config.meili_index_uid)
            game_index.delete_index()
            game_index = MeiliGameIndex(
                url=config.meili_url,
                api_key=config.meili_api_key,
                index_uid=config.meili_index_uid,
                embedder_name="bge_m3",
                embedding_dim=1024,
            )

    game_index.ensure_settings()

    existing_names = set()
    start_id = 1
    if mode == "append":
        logging.info("Mode=append: fetching existing names for deduplication...")
        existing_names, max_id = game_index.fetch_existing_names_and_max_id()
        start_id = max_id + 1
        before_filter = len(names)
        names = [n for n in names if n not in existing_names]
        logging.info(
            "Append mode: %d new names after filtering %d existing; start id=%d",
            len(names),
            before_filter - len(names),
            start_id,
        )
        if not names:
            logging.warning("No new names to append; exiting.")
            return

    embedder = BgeM3Embedder(model_name=config.bge_model_name, use_fp16=config.bge_use_fp16)

    docs_batch = []
    next_id = start_id
    for start in range(0, len(names), config.encode_batch_size):
        batch_names = names[start : start + config.encode_batch_size]
        logging.debug("Encoding batch [%d:%d) size=%d", start, start + len(batch_names), len(batch_names))
        dense_vecs = embedder.encode_dense(
            batch_names,
            batch_size=len(batch_names),
            max_length=128,
        )

        for name, vec in zip(batch_names, dense_vecs):
            doc = {
                "id": next_id,
                "name": name,
                "_vectors": {"bge_m3": vec.tolist()},
            }
            docs_batch.append(doc)
            next_id += 1

            if len(docs_batch) >= config.index_batch_size:
                logging.info("Writing %d documents (up to id=%d)", len(docs_batch), next_id - 1)
                logging.debug("First doc of batch: %s", docs_batch[0])
                game_index.add_documents(docs_batch)
                docs_batch = []

    if docs_batch:
        logging.info("Writing final %d documents (up to id=%d)", len(docs_batch), next_id - 1)
        logging.debug("First doc of final batch: %s", docs_batch[0])
        game_index.add_documents(docs_batch)

    elapsed = time.time() - start_time
    logging.info("Index build completed in %.2fs", elapsed)
