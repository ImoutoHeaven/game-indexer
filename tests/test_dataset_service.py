from pathlib import Path

import pytest

from game_web.services import dataset_service


class _Conn:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("boom")


def test_save_upload_cleans_file_when_insert_fails(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = _Conn()

    file_obj = _FileObj(b"hello")

    with pytest.raises(RuntimeError):
        dataset_service.save_upload(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            file_obj=file_obj,
            commit=False,
        )

    upload_path = data_dir / "uploads" / "1" / "games.txt"
    assert not upload_path.exists()


class _FileObj:
    def __init__(self, content: bytes):
        self._content = content
        self._offset = 0

    def read(self, size: int) -> bytes:
        if self._offset >= len(self._content):
            return b""
        if size <= 0:
            size = len(self._content)
        start = self._offset
        end = min(start + size, len(self._content))
        self._offset = end
        return self._content[start:end]
