from pathlib import Path

from aido.worker.queue import InboxQueue


def test_put_get_roundtrip():
    q = InboxQueue()
    q.put(Path("/scans/a.pdf"))
    assert q.get(timeout=0.1) == Path("/scans/a.pdf")


def test_get_returns_none_on_timeout():
    q = InboxQueue()
    assert q.get(timeout=0.05) is None


def test_drain_existing_enqueues_pdfs(tmp_path: Path):
    (tmp_path / "a.pdf").touch()
    (tmp_path / "b.PDF").touch()  # case-insensitive
    (tmp_path / "ignore.txt").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.pdf").touch()  # nested ignored

    q = InboxQueue()
    q.drain_existing(tmp_path)
    seen = set()
    while item := q.get(timeout=0.05):
        seen.add(item.name)
    assert seen == {"a.pdf", "b.PDF"}


def test_drain_existing_skips_hidden_files(tmp_path: Path):
    (tmp_path / ".hidden.pdf").touch()
    (tmp_path / "real.pdf").touch()
    q = InboxQueue()
    q.drain_existing(tmp_path)
    seen = []
    while item := q.get(timeout=0.05):
        seen.append(item.name)
    assert seen == ["real.pdf"]
