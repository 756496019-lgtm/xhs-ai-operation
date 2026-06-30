"""小红书 Cookie 解析测试。"""

from xhs_publisher import _parse_cookie


def test_parse_standard_cookie():
    result = _parse_cookie("a1=abc; web_session=xyz")
    assert result == {"a1": "abc", "web_session": "xyz"}


def test_parse_empty_string():
    assert _parse_cookie("") == {}


def test_parse_none():
    assert _parse_cookie(None) == {}


def test_parse_with_spaces():
    result = _parse_cookie("  key1 = val1 ; key2=val2  ")
    assert result == {"key1": "val1", "key2": "val2"}


def test_parse_value_with_equals():
    result = _parse_cookie("token=abc=def=ghi")
    assert result == {"token": "abc=def=ghi"}


def test_parse_single_item():
    result = _parse_cookie("a1=test123")
    assert result == {"a1": "test123"}


def test_parse_item_without_equals():
    result = _parse_cookie("a1=abc; invalid; key2=val2")
    assert result == {"a1": "abc", "key2": "val2"}
