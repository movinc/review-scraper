"""Tests for main._run_scrape() retry logic and on_progress callbacks."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Patch db before importing main."""
    import main
    mock = MagicMock()
    mock.get_job.return_value = {"status": "running"}
    monkeypatch.setattr(main, "db", mock)
    return mock


def get_mock_db():
    import main
    return main.db


# ── _run_scrape tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scrape_success(monkeypatch):
    """スクレイパーがレビューを返す → status=done"""
    import main
    from models import Source, JobStatus

    reviews = [{"text": "good"}] * 3
    scraper = MagicMock(return_value=reviews)
    monkeypatch.setattr(main, "scrape_google_reviews", scraper)

    await main._run_scrape("job1", "https://maps.google.com/test", Source.google)

    db = get_mock_db()
    calls = [str(c) for c in db.update_job.call_args_list]
    assert any("done" in c for c in calls), f"Expected done in calls: {calls}"


@pytest.mark.asyncio
async def test_scrape_zero_retry(monkeypatch):
    """スクレイパーが常に0件 → MAX_OUTER_RETRIES 後に done(0件)"""
    import main
    from models import Source, JobStatus

    scraper = MagicMock(return_value=[])
    monkeypatch.setattr(main, "scrape_google_reviews", scraper)

    await main._run_scrape("job2", "https://maps.google.com/test", Source.google)

    db = get_mock_db()
    # scraper should be called MAX_OUTER_RETRIES times
    assert scraper.call_count == 3
    calls = [str(c) for c in db.update_job.call_args_list]
    assert any("done" in c for c in calls)


@pytest.mark.asyncio
async def test_scrape_error_then_success(monkeypatch):
    """1回目例外 → 2回目成功 → done"""
    import main
    from models import Source

    scraper = MagicMock(side_effect=[RuntimeError("boom"), [{"text": "ok"}]])
    monkeypatch.setattr(main, "scrape_google_reviews", scraper)

    await main._run_scrape("job3", "https://maps.google.com/test", Source.google)

    db = get_mock_db()
    assert scraper.call_count == 2
    calls = [str(c) for c in db.update_job.call_args_list]
    assert any("done" in c for c in calls)


@pytest.mark.asyncio
async def test_scrape_timeout_no_retry(monkeypatch):
    """タイムアウト → リトライなし → failed"""
    import main
    from models import Source

    async def fake_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    scraper = MagicMock(return_value=[{"text": "x"}])
    monkeypatch.setattr(main, "scrape_google_reviews", scraper)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await main._run_scrape("job4", "https://maps.google.com/test", Source.google)

    db = get_mock_db()
    # scraper should only be called once (no retry on timeout)
    assert scraper.call_count <= 1
    calls = [str(c) for c in db.update_job.call_args_list]
    assert any("failed" in c for c in calls)


@pytest.mark.asyncio
async def test_progress_extracts_gyazo(monkeypatch):
    """on_progress が Gyazo URL を last_screenshot に保存する"""
    import main
    from models import Source

    captured_extra = {}
    orig_update = get_mock_db().update_job

    def capturing_update(job_id, **kwargs):
        if "last_screenshot" in kwargs:
            captured_extra["last_screenshot"] = kwargs["last_screenshot"]

    get_mock_db().update_job.side_effect = capturing_update

    gyazo_url = "https://gyazo.com/abc123def456abc123def456abc12345"

    # Simulate a scraper that calls on_progress with a Gyazo message then returns reviews
    def fake_scraper(url, on_progress, on_reviews):
        on_progress(1, f"📸 {gyazo_url}")
        return [{"text": "x"}]

    monkeypatch.setattr(main, "scrape_google_reviews", fake_scraper)

    await main._run_scrape("job5", "https://maps.google.com/test", Source.google)

    assert captured_extra.get("last_screenshot") == gyazo_url


@pytest.mark.asyncio
async def test_progress_detects_cancel(monkeypatch):
    """on_progress がキャンセル状態を検出して RuntimeError を上げる → failed"""
    import main
    from models import Source, JobStatus

    call_count = [0]

    def fake_get_job(job_id):
        call_count[0] += 1
        return {"status": "cancelled"}

    get_mock_db().get_job.side_effect = fake_get_job

    cancelled = [False]

    def fake_scraper(url, on_progress, on_reviews):
        # Call on_progress 5 times to trigger the cancellation check (every 5 calls)
        for i in range(5):
            try:
                on_progress(i, "progress message")
            except RuntimeError:
                cancelled[0] = True
                raise
        return [{"text": "x"}]

    monkeypatch.setattr(main, "scrape_google_reviews", fake_scraper)

    await main._run_scrape("job6", "https://maps.google.com/test", Source.google)

    assert cancelled[0], "Expected RuntimeError from cancel detection"
