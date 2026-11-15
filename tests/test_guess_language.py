import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spotify import guess_language


def test_english_title_is_en():
    assert guess_language("Medieval Heraldry Incomplet Design History") == "en"


def test_japanese_title_is_ja():
    assert guess_language("Vol.237 身体の知を受け継ぐ日本の方法 TAKRAM RADIO") == "ja"


def test_katakana_only_is_ja():
    assert guess_language("デザインラジオ") == "ja"


def test_empty_is_en():
    assert guess_language("") == "en"
