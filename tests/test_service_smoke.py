from game_semantic import service


def test_service_exports_wrappers():
    assert callable(service.build_index)
    assert callable(service.search_games)
    assert callable(service.dedupe_items)
