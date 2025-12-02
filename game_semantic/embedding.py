"""BGE-M3 embedding wrapper."""

from typing import List

import numpy as np
from FlagEmbedding import BGEM3FlagModel


class BgeM3Embedder:
    """Encapsulates BGEM3FlagModel for dense encoding."""

    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = False):
        self.model = BGEM3FlagModel(model_name, use_fp16=use_fp16)

    def encode_dense(self, texts: List[str], batch_size: int = 64, max_length: int = 128) -> np.ndarray:
        """
        Encode a list of texts into dense vectors.

        Returns a numpy array with shape (len(texts), 1024). Empty input returns
        an empty array with the same second dimension.
        """
        if not texts:
            return np.zeros((0, 1024), dtype=np.float32)

        encoded = self.model.encode(
            texts,
            batch_size=batch_size,
            max_length=max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense_vecs = encoded["dense_vecs"]
        return dense_vecs
