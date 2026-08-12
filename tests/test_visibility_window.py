"""Compatibility disclosure for the visibility summary window argument."""
from aeko_mcp.tools import visibility


def _metrics_payload():
    return {
        "total_mentions": 4,
        "total_citations": 2,
        "avg_sentiment_score": 75.0,
        "data_points_current": 6,
        "data_points_previous": 5,
    }


def test_tracked_metrics_discloses_ignored_non_7d_window(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return _metrics_payload()

    monkeypatch.setattr(visibility.client, "get", fake_get)
    output = visibility.aeko_get_visibility_summary(
        "domain-1",
        scope="tracked_prompt_metrics",
        window="30d",
    )

    assert calls == [
        ("/api/tracked-prompts/metrics", {"domain_id": "domain-1"})
    ]
    assert output.startswith(
        "> Requested window `30d` ignored — this endpoint is fixed at 7 days by the backend."
    )
    assert "# Performance Metrics (Last 7 Days)" in output


def test_tracked_metrics_does_not_warn_for_7d_or_omitted_window(monkeypatch):
    monkeypatch.setattr(
        visibility.client,
        "get",
        lambda *args, **kwargs: _metrics_payload(),
    )

    for window in (None, "7d"):
        output = visibility.aeko_get_visibility_summary(
            "domain-1",
            scope="tracked_prompt_metrics",
            window=window,
        )
        assert "Requested window" not in output
        assert output.startswith("# Performance Metrics (Last 7 Days)")


def test_overview_keeps_window_out_of_backend_params(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {"brand_keyword": "AEKO", "metrics": {}}

    monkeypatch.setattr(visibility.client, "get", fake_get)
    visibility.aeko_get_visibility_summary("domain-1", window="90d")

    assert calls == [
        ("/api/visibility/summary", {"domain_id": "domain-1"})
    ]
