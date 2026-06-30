"""Reddit 抓取模块测试。"""

from unittest.mock import patch, MagicMock
from scrapers.reddit import fetch_reddit_top_week


@patch("scrapers.reddit.feedparser.parse")
def test_returns_empty_on_exception(mock_parse):
    mock_parse.side_effect = Exception("network error")
    result = fetch_reddit_top_week("game", "gaming", 5)
    assert result == []


@patch("scrapers.reddit.feedparser.parse")
def test_returns_empty_on_no_entries(mock_parse):
    mock_parse.return_value = MagicMock(entries=[])
    result = fetch_reddit_top_week("game", "gaming", 5)
    assert result == []


@patch("scrapers.reddit.feedparser.parse")
def test_deduplicates_entries(mock_parse):
    entry = MagicMock()
    entry.id = "dup-id"
    entry.title = "Test Post"
    entry.summary = "Summary text"
    entry.link = "https://reddit.com/r/gaming/1"
    entry.author = "user1"
    entry.published_parsed = (2025, 3, 15, 12, 0, 0, 0, 0, 0)
    entry.updated_parsed = None
    mock_parse.return_value = MagicMock(entries=[entry, entry])
    result = fetch_reddit_top_week("game", "gaming", 5)
    assert len(result) == 1
    assert result[0]["title"] == "Test Post"


@patch("scrapers.reddit.feedparser.parse")
def test_respects_limit(mock_parse):
    entries = []
    for i in range(10):
        e = MagicMock()
        e.id = f"id-{i}"
        e.title = f"Post {i}"
        e.summary = "Summary"
        e.link = f"https://reddit.com/r/gaming/{i}"
        e.author = "user"
        e.published_parsed = (2025, 3, 15, 12, i, 0, 0, 0, 0)
        e.updated_parsed = None
        entries.append(e)
    mock_parse.return_value = MagicMock(entries=entries)
    result = fetch_reddit_top_week("game", "gaming", 3)
    assert len(result) == 3


@patch("scrapers.reddit.feedparser.parse")
def test_skips_entries_without_time(mock_parse):
    entry = MagicMock()
    entry.id = "no-time"
    entry.title = "No Time"
    entry.summary = "Text"
    entry.link = "https://reddit.com/r/gaming/x"
    entry.author = "user"
    entry.published_parsed = None
    entry.updated_parsed = None
    mock_parse.return_value = MagicMock(entries=[entry])
    result = fetch_reddit_top_week("game", "gaming", 5)
    assert result == []
