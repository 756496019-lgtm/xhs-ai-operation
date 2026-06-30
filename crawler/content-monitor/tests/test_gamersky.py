"""游民星空日期匹配与内容提取测试。"""

import pytest
from scrapers.gamersky import GamerskyScraperLite


class TestIsTargetDate:
    def setup_method(self):
        self.scraper = GamerskyScraperLite("2025-03-15")

    def test_matches_dash_format(self):
        assert self.scraper.is_target_date("2025-03-15") is True

    def test_matches_dash_no_leading_zero(self):
        assert self.scraper.is_target_date("2025-3-15") is True

    def test_matches_slash_format(self):
        assert self.scraper.is_target_date("2025/3/15") is True

    def test_matches_chinese_format(self):
        assert self.scraper.is_target_date("2025年3月15日") is True

    def test_matches_with_surrounding_text(self):
        assert self.scraper.is_target_date("发布于 2025-03-15 14:00") is True

    def test_rejects_different_day(self):
        assert self.scraper.is_target_date("2025-03-16") is False

    def test_rejects_different_month(self):
        assert self.scraper.is_target_date("2025-04-15") is False

    def test_rejects_different_year(self):
        assert self.scraper.is_target_date("2024-03-15") is False

    def test_rejects_empty(self):
        assert self.scraper.is_target_date("") is False

    def test_rejects_none(self):
        assert self.scraper.is_target_date(None) is False

    def test_rejects_no_date_text(self):
        assert self.scraper.is_target_date("这是一段没有日期的文字") is False


class TestIsTargetDateEdgeCases:
    def test_single_digit_day(self):
        scraper = GamerskyScraperLite("2025-01-05")
        assert scraper.is_target_date("2025-1-5") is True
        assert scraper.is_target_date("2025/01/05") is True

    def test_december(self):
        scraper = GamerskyScraperLite("2025-12-31")
        assert scraper.is_target_date("2025年12月31日") is True
