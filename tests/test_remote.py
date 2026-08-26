"""remote.py's fallback contract: GitHub main wins when reachable, local disk otherwise --
real-but-old over invented, same doctrine as the price cache. Network is monkeypatched
out entirely; no test here ever calls the real GitHub API.

tests/conftest.py's autouse _no_real_network fixture already blocks remote._get and
clears remote._cache before/after every test in the suite; these tests override _get
per-test to exercise specific branches."""
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


def test_second_call_within_ttl_serves_from_cache_not_a_new_request(monkeypatch):
    """The whole point of caching (#229): flipping between dashboard pages within
    CACHE_SECONDS must not pay a fresh network round trip per file."""
    calls = []
    monkeypatch.setattr(remote, "_get", lambda url: calls.append(url) or b"data")

    remote.read_bytes("graveyard.csv")
    remote.read_bytes("graveyard.csv")
    assert len(calls) == 1


def test_ttl_zero_bypasses_the_cache(monkeypatch):
    """A caller that must see a just-written row on the very next call (the factory's
    own ledgers, see dashboard._load_generated_ledger()) passes ttl=0."""
    calls = []
    monkeypatch.setattr(remote, "_get", lambda url: calls.append(url) or b"data")

    remote.read_bytes("generated_templates.csv", ttl=0)
    remote.read_bytes("generated_templates.csv", ttl=0)
    assert len(calls) == 2


def test_read_json_parses_remote_content(monkeypatch):
    monkeypatch.setattr(remote, "_get", lambda url: b'{"a": 1}')
    assert remote.read_json("state/paper/carry_risk.json") == {"a": 1}


def test_read_json_none_when_missing_everywhere(monkeypatch, tmp_path):
    monkeypatch.setattr(remote, "_get", lambda url: (_ for _ in ()).throw(OSError("404")))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    assert remote.read_json("state/paper/carry_risk.json") is None
