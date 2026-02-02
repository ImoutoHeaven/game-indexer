"""Lightweight Meilisearch wrapper for game indexing and search."""

import logging
from typing import Any, Dict, List

import meilisearch
try:  # SDK versions differ on exported error types
    from meilisearch.errors import MeiliSearchApiError
except Exception:  # noqa: BLE001
    MeiliSearchApiError = Exception  # type: ignore[misc,assignment]


class MeiliGameIndex:
    """Helper around a Meilisearch index configured for BGE-M3 vectors."""

    def __init__(
        self,
        url: str,
        api_key: str,
        index_uid: str = "games",
        embedder_name: str = "bge_m3",
        embedding_dim: int = 1024,
        displayed_attributes: list[str] | None = None,
        searchable_attributes: list[str] | None = None,
    ):
        self.client = meilisearch.Client(url, api_key)
        self.index_uid = index_uid
        self.embedder_name = embedder_name
        self.embedding_dim = embedding_dim
        self.displayed_attributes = displayed_attributes or ["id", "name"]
        self.searchable_attributes = searchable_attributes or ["name"]
        self.index = self._get_or_create_index()

    @staticmethod
    def _extract_results(data):
        """Normalize SDK responses to a list of dicts."""
        def _as_list(value):
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
            return []

        if isinstance(data, dict):
            if "results" in data:
                return _as_list(data.get("results"))
            if "hits" in data:
                return _as_list(data.get("hits"))
        if isinstance(data, list):
            return data
        results = getattr(data, "results", None)
        if results is not None:
            return _as_list(results)
        to_dict = getattr(data, "dict", None)
        if callable(to_dict):
            try:
                converted = to_dict()
                if isinstance(converted, dict):
                    if "results" in converted:
                        return _as_list(converted.get("results"))
                    if "hits" in converted:
                        return _as_list(converted.get("hits"))
            except Exception as exc:
                logging.debug("to_dict failed in _extract_results: %s", exc)
        if hasattr(data, "__dict__"):
            maybe = data.__dict__.get("results") or data.__dict__.get("hits")
            if maybe is not None:
                return _as_list(maybe)
        return []

    def _get_or_create_index(self):
        """Return an Index object, creating the index when missing."""
        index = self.client.index(self.index_uid)

        # Validate existence
        try:
            if hasattr(index, "get_raw_info"):
                index.get_raw_info()
            else:
                index.get_stats()
            return index
        except Exception as exc:
            if isinstance(exc, MeiliSearchApiError) and getattr(exc, "code", None) == "index_not_found":
                logging.info("Index %s missing; creating.", self.index_uid)
            else:
                raise

        # Create index if missing
        try:
            self.client.create_index(uid=self.index_uid, options={"primaryKey": "id"})
        except Exception as exc:  # noqa: BLE001
            # If already exists or other races, proceed to return index anyway
            logging.debug("create_index returned %s", exc)
        return self.client.index(self.index_uid)

    def delete_index(self):
        """Delete the index if it exists."""
        try:
            self.client.delete_index(self.index_uid)
            logging.info("Deleted index %s", self.index_uid)
        except MeiliSearchApiError as exc:
            if getattr(exc, "code", None) == "index_not_found":
                logging.info("Index %s not found; nothing to delete.", self.index_uid)
            else:
                logging.warning("Failed to delete index %s: %s", self.index_uid, exc)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to delete index %s: %s", self.index_uid, exc)

    def fetch_existing_names_and_max_id(self, page_size: int = 1000):
        """
        Fetch existing documents' names and max id for append/dedup purposes.

        Returns (names_set, max_id).
        """
        names = set()
        max_id = 0
        offset = 0

        while True:
            try:
                data = self.index.get_documents(
                    {
                        "offset": offset,
                        "limit": page_size,
                        "fields": ["id", "name"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to fetch documents for dedup: %s", exc)
                break

            docs = self._extract_results(data)
            if not docs:
                break

            for doc in docs:
                name = doc.get("name") if isinstance(doc, dict) else getattr(doc, "name", None)
                doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
                if name:
                    names.add(name)
                if isinstance(doc_id, int) and doc_id > max_id:
                    max_id = doc_id

            offset += len(docs)
            if len(docs) < page_size:
                break

        logging.debug("Fetched %d existing names, max_id=%d", len(names), max_id)
        return names, max_id

    def fetch_all_names_list(self, page_size: int = 1000):
        """
        Fetch all document names as an ordered list (may include duplicates).
        """
        all_names: List[str] = []
        offset = 0

        while True:
            try:
                data = self.index.get_documents(
                    {
                        "offset": offset,
                        "limit": page_size,
                        "fields": ["name"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to fetch documents for refine: %s", exc)
                break

            docs = self._extract_results(data)
            if not docs:
                break

            for doc in docs:
                name = doc.get("name") if isinstance(doc, dict) else getattr(doc, "name", None)
                if name:
                    all_names.append(name)

            offset += len(docs)
            if len(docs) < page_size:
                break

        logging.debug("Fetched %d names for refine", len(all_names))
        return all_names

    def ensure_settings(self):
        """
        Ensure embedders/searchable/displayed settings exist.

        Logs warnings instead of raising if the Meilisearch version lacks support.
        """
        target_embedder = {
            self.embedder_name: {
                "source": "userProvided",
                "dimensions": self.embedding_dim,
            }
        }

        try:
            current = self.index.get_settings()
        except Exception as exc:  # noqa: BLE001
            logging.warning("Unable to read index settings: %s", exc)
            current = {}
        else:
            logging.debug("Current settings keys: %s", list(current.keys()) if isinstance(current, dict) else current)
            if not isinstance(current, dict):
                current = {}

        updates: Dict[str, Any] = {}

        existing_embedders = (current or {}).get("embedders") or {}
        if existing_embedders.get(self.embedder_name) != target_embedder[self.embedder_name]:
            merged = dict(existing_embedders)
            merged.update(target_embedder)
            updates["embedders"] = merged

        if current.get("searchableAttributes") != self.searchable_attributes:
            updates["searchableAttributes"] = self.searchable_attributes

        if current.get("displayedAttributes") != self.displayed_attributes:
            updates["displayedAttributes"] = self.displayed_attributes

        if not updates:
            logging.debug("No settings changes required.")
            return

        try:
            self.index.update_settings(updates)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to update index settings (likely unsupported): %s", exc)
        else:
            logging.debug("Settings update sent: %s", updates)

    def add_documents(self, docs: List[Dict[str, Any]], wait: bool = False):
        """Add a batch of documents to the index."""
        if not docs:
            return
        logging.debug("Adding %d documents", len(docs))
        target_index = self.index
        if not hasattr(target_index, "add_documents"):
            target_index = self.client.index(self.index_uid)
        task = target_index.add_documents(docs)
        if wait:
            task_uid = None
            if isinstance(task, dict):
                task_uid = task.get("uid") or task.get("taskUid") or task.get("updateId")
            try:
                if task_uid is not None and hasattr(self.client, "wait_for_task"):
                    self.client.wait_for_task(task_uid)
            except Exception as exc:  # noqa: BLE001
                logging.debug("wait_for_task failed: %s", exc)

    def fetch_documents(self, fields: list[str] | None = None, page_size: int = 1000) -> list[dict]:
        """
        Retrieve all documents with optional field selection.
        """
        results: list[dict] = []
        offset = 0
        while True:
            try:
                data = self.index.get_documents(
                    {
                        "offset": offset,
                        "limit": page_size,
                        "fields": fields,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to fetch documents: %s", exc)
                break

            docs = self._extract_results(data)
            if not docs:
                break

            results.extend(docs)
            offset += len(docs)
            if len(docs) < page_size:
                break

        logging.debug("Fetched %d documents (fields=%s)", len(results), fields or "all")
        return results

    def search_by_vector(
        self,
        query_vector: List[float],
        limit: int = 10,
        embedder_key: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Search using a dense vector with embedder-aware payload."""
        target_embedder = embedder_key or self.embedder_name
        payload = {
            "vector": query_vector,
            "hybrid": {"semanticRatio": 1.0, "embedder": target_embedder},
            "limit": limit,
        }

        try:
            result = self.index.search("", payload)
            hits = result.get("hits", [])
            logging.debug("Vector search succeeded with %d hits", len(hits))
            return hits
        except Exception as exc:  # noqa: BLE001
            logging.warning("Vector search failed; returning empty list: %s", exc)
            return []
