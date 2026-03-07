"""Shared pytest fixtures for review-scraper tests."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db(monkeypatch):
    """Mock all db module functions used in main._run_scrape."""
    import main
    mock = MagicMock()
    mock.get_job.return_value = {"status": "running"}
    monkeypatch.setattr(main, "db", mock)
    return mock


@pytest.fixture
def mock_scraper_success():
    """Scraper that returns 5 reviews."""
    return MagicMock(return_value=[{"text": f"review {i}"} for i in range(5)])


@pytest.fixture
def mock_scraper_zero():
    """Scraper that always returns 0 reviews."""
    return MagicMock(return_value=[])


@pytest.fixture
def mock_scraper_error():
    """Scraper that raises RuntimeError."""
    return MagicMock(side_effect=RuntimeError("scrape error"))
