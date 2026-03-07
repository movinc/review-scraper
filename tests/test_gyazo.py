"""Tests for utils/gyazo.py upload_screenshot."""
import pytest
from unittest.mock import MagicMock, patch
import json


def test_upload_no_token(monkeypatch):
    """GYAZO_ACCESS_TOKEN未設定 → None"""
    import utils.gyazo as gyazo_mod
    monkeypatch.setattr(gyazo_mod, "GYAZO_ACCESS_TOKEN", "")
    result = gyazo_mod.upload_screenshot(MagicMock())
    assert result is None


def test_upload_success(monkeypatch):
    """mock httpでURL返す → URLが返る"""
    import utils.gyazo as gyazo_mod
    monkeypatch.setattr(gyazo_mod, "GYAZO_ACCESS_TOKEN", "test-token")

    mock_page = MagicMock()
    mock_page.screenshot.return_value = b"\x89PNG\r\n"

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "permalink_url": "https://gyazo.com/abc123"
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("utils.gyazo.urlopen", return_value=mock_response):
        result = gyazo_mod.upload_screenshot(mock_page, title="test")

    assert result == "https://gyazo.com/abc123"


def test_upload_failure(monkeypatch):
    """urlopen が例外 → None"""
    import utils.gyazo as gyazo_mod
    monkeypatch.setattr(gyazo_mod, "GYAZO_ACCESS_TOKEN", "test-token")

    mock_page = MagicMock()
    mock_page.screenshot.return_value = b"\x89PNG\r\n"

    with patch("utils.gyazo.urlopen", side_effect=Exception("network error")):
        result = gyazo_mod.upload_screenshot(mock_page)

    assert result is None
