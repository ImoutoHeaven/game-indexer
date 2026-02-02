def build_query_payload(query_vector, limit: int, embedder_key: str):
    return {
        "vector": query_vector,
        "hybrid": {"semanticRatio": 1.0, "embedder": embedder_key},
        "limit": limit,
    }
