import pytest

from scout.data.patch import display_patch, from_display_label, is_newer, short_patch


def test_short_patch():
    assert short_patch("16.19.1") == "16.19"


def test_display_patch_is_year_based_from_2025():
    assert display_patch("16.19.1") == "26.19"
    assert display_patch("16.19") == "26.19"
    assert display_patch("15.1.1") == "25.1"
    assert display_patch("14.5.1") == "14.5"  # 2024 and earlier: same number


def test_from_display_label():
    assert from_display_label("V26.12") == "16.12"
    assert from_display_label("26.19") == "16.19"
    assert from_display_label("V14.5") == "14.5"


def test_is_newer_compares_numerically():
    assert is_newer("16.19.1", "16.9.1")
    assert not is_newer("16.18.1", "16.19.1")


@pytest.mark.parametrize("bad", ["", "16", "v16.x", "abc"])
def test_bad_versions_raise(bad):
    with pytest.raises(ValueError):
        short_patch(bad)
