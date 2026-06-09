from __future__ import annotations

from zeropark_core.config import ZeroparkSettings


def test_defaults_have_no_search_backend() -> None:
    s = ZeroparkSettings(_env_file=None)
    assert s.output_dir == "artifacts"
    assert s.search.base_url is None
    assert s.search_kwargs() is None


def test_env_configures_search_and_output(monkeypatch) -> None:
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", "/tmp/out")
    monkeypatch.setenv("ZEROPARK_SEARCH__BASE_URL", "https://api.example.com/search")
    monkeypatch.setenv("ZEROPARK_SEARCH__API_KEY", "k")
    s = ZeroparkSettings(_env_file=None)
    assert s.output_dir == "/tmp/out"
    assert s.search_kwargs() == {
        "base_url": "https://api.example.com/search",
        "api_key": "k",
        "query_param": "q",
        "results_key": "results",
    }
