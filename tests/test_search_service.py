from game_web.services.search_service import build_query_payload


def test_build_query_payload_includes_embedder():
    payload = build_query_payload([0.1, 0.2], limit=3, embedder_key="v_alias")
    assert payload["hybrid"]["embedder"] == "v_alias"
