def build_index(config):
    from game_semantic.index_builder import build_index as _build_index

    return _build_index(config)


def search_games(config):
    from game_semantic.search_cli import interactive_search as _interactive_search

    return _interactive_search(config)


def dedupe_items(
    items,
    *,
    config,
    mode,
    threshold,
    top_k,
    check_ctime,
    check_mtime,
    check_size,
    time_window,
):
    from game_semantic.deduper import dedupe_items as _dedupe_items

    return _dedupe_items(
        items,
        config=config,
        mode=mode,
        threshold=threshold,
        top_k=top_k,
        check_ctime=check_ctime,
        check_mtime=check_mtime,
        check_size=check_size,
        time_window=time_window,
    )
