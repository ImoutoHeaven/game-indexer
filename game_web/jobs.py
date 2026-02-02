def write_log_line(path: str, line: str) -> None:
    """Append a single line (newlines normalized to spaces), UTF-8."""
    normalized = line.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(normalized + "\n")
