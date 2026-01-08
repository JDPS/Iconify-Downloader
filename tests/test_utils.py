import pytest
from click import ClickException

from iconify_downloader.utils import filter_icons, infer_prefix


def test_infer_prefix_valid():
    assert infer_prefix("fluent") == "fluent"
    assert infer_prefix("https://icon-sets.iconify.design/fluent/") == "fluent"
    assert infer_prefix("https://iconify.design/icon-sets/fluent/") == "fluent"
    assert infer_prefix("iconify.design/icon-sets/fluent") == "fluent"
    # raw json url case if we want to support it? The function seems to handle it via url parsing
    assert infer_prefix("https://raw.githubusercontent.com/iconify/icon-sets/master/json/fluent.json") == "fluent"

def test_infer_prefix_invalid():
    with pytest.raises(ClickException):
        infer_prefix("invalid prefix with spaces")
    
    with pytest.raises(ClickException):
        infer_prefix("http://example.com/random/path with spaces")

def test_filter_icons():
    icons = ["arrow-left", "arrow-right", "home", "user"]
    
    # Test include
    assert filter_icons(icons, include={"arrow-left", "home"}, exclude=None, contains=None) == ["arrow-left", "home"]
    
    # Test exclude
    assert filter_icons(icons, include=None, exclude={"arrow-right", "user"}, contains=None) == ["arrow-left", "home"]
    
    # Test contains
    assert filter_icons(icons, include=None, exclude=None, contains="arrow") == ["arrow-left", "arrow-right"]
    
    # Test combination
    assert filter_icons(icons, include=None, exclude={"arrow-right"}, contains="arrow") == ["arrow-left"]
