import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "local_transcriber"))

from transcriber import strip_fake_speaker_labels  # noqa: E402


def test_removes_labels_from_ep050_style_text():
    text = "初めて聞いた樋口 ナイス樋口 びっくりしててAI詳しいんだと思って深井 そうねそこそこ深井 詳しいです"
    cleaned, n = strip_fake_speaker_labels(text)
    assert n == 4
    assert "深井" not in cleaned and "樋口" not in cleaned
    assert cleaned == "初めて聞いた ナイス びっくりしててAI詳しいんだと思って そうねそこそこ 詳しいです"


def test_removes_label_at_segment_start_and_after_laugh():
    assert strip_fake_speaker_labels("ヤンヤン 鼻高くなったよね") == ("鼻高くなったよね", 1)
    cleaned, n = strip_fake_speaker_labels("（笑）笑深井 そうそう")
    assert n == 1 and "深井" not in cleaned


def test_removes_label_dangling_at_line_end():
    cleaned, n = strip_fake_speaker_labels("ほんとですか深井\nそうなんです大変ヤンヤン")
    assert n == 2
    assert cleaned == "ほんとですか\nそうなんです大変"


def test_removes_bracketed_label():
    assert strip_fake_speaker_labels("心がけています【ヤンヤン】なるほど") == ("心がけています なるほど", 1)


def test_keeps_real_name_mentions():
    for text in ["深井さんが言ってた", "深井龍之介さん", "深井 龍之介さんがゲスト", "樋口 聖典さん",
                 "樋口さんとヤンヤンさん", "深井:「あっ、素晴らしい」"]:
        assert strip_fake_speaker_labels(text) == (text, 0)


def test_idempotent_and_empty():
    once, _ = strip_fake_speaker_labels("深井 削ります中を樋口 は?")
    assert strip_fake_speaker_labels(once) == (once, 0)
    assert strip_fake_speaker_labels("") == ("", 0)
    assert strip_fake_speaker_labels(None) == (None, 0)
