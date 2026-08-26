"""remote.py's fallback contract: GitHub main wins when reachable, local disk otherwise --
real-but-old over invented, same doctrine as the price cache. Network is monkeypatched
out entirely; no test here ever calls the real GitHub API."""
from tradefabe import remote


def test_prefers_github_content_when_reachable(monkeypatch):
    monkeypatch.setattr(remote, "_get", lambda url: b"remote,content\n1,2\n")
    assert remote.read_bytes("graveyard.csv") == b"remote,content\n1,2\n"


def test_falls_back_to_local_disk_on_network_failure(monkeypatch, tmp_path):
    def _boom(url):
        raise OSError("network unreachable")

    monkeypatch.setattr(remote, "_get", _boom)
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    (tmp_path / "graveyard.csv").write_bytes(b"local,content\n3,4\n")

    assert remote.read_bytes("graveyard.csv") == b"local,content\n3,4\n"


def test_returns_none_when_neither_source_has_it(monkeypatch, tmp_path):
    monkeypatch.setattr(remote, "_get", lambda url: (_ for _ in ()).throw(OSError("404")))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)

    assert remote.read_bytes("nope.csv") is None
    assert remote.exists("nope.csv") is False


def test_fetches_fresh_every_call_no_caching(monkeypatch):
    """A freshly-committed row must show up on the very next request -- see the
    module docstring on why this file caches nothing."""
    calls = []
    monkeypatch.setattr(remote, "_get", lambda url: calls.append(url) or b"data")

    remote.read_bytes("graveyard.csv")
    remote.read_bytes("graveyard.csv")
    assert len(calls) == 2


def test_read_json_parses_remote_content(monkeypatch):
    monkeypatch.setattr(remote, "_get", lambda url: b'{"a": 1}')
    assert remote.read_json("state/paper/carry_risk.json") == {"a": 1}


def test_read_json_none_when_missing_everywhere(monkeypatch, tmp_path):
    monkeypatch.setattr(remote, "_get", lambda url: (_ for _ in ()).throw(OSError("404")))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    assert remote.read_json("state/paper/carry_risk.json") is None
