"""Verification layer for generated podcast notes.

Why this exists
---------------
Until now every quality problem in the output was found by a human reading the
finished Notion page: Whisper mangling proper nouns, Gemini leaking a
"承知いたしました" preamble into the Summary, transcript fragments ending up as
chapter titles. The pipeline generated confidently and never checked itself, so
the reviewer was the only verification step.

This module is that missing step. It runs after generation and before the human
looks at anything, and it does two independent kinds of checking:

1. **External grounding** — pull the show's own episode notes from its RSS feed
   (``content:encoded`` / ``description``) and treat the proper nouns there as
   ground truth. Any official term absent from the transcript is a likely
   Whisper misrecognition. This is exactly the manual "open the show notes and
   compare" pass, automated.

2. **Self-consistency checks** — deterministic assertions about the generated
   Summary / Key Takeaways / chapter titles that encode bugs we have actually
   shipped before. These need no network and no LLM.

Only step 1's *naming* of the garbled form uses Gemini, and it is capped at a
single call. Everything else degrades gracefully: no network, no RSS entry, or
no Gemini still yields a useful report.

Note on trust: official show notes are authored by humans and contain their own
typos (fukabori.fm #139 writes "スキュアモーフィズム" for スキューモーフィズム).
Treat the report as *candidates for a human to confirm*, never as auto-applied
edits — which is why nothing here rewrites the transcript.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

import requests

CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"
ITUNES_SUMMARY = "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary"

# Boilerplate that appears in RSS notes but is never spoken aloud.
_TERM_STOPWORDS = {
    "see", "privacy", "policy", "california", "notice", "and", "at", "the", "a",
    "an", "of", "for", "to", "in", "on", "do", "not", "sell", "my", "info",
    "https", "http", "www", "com", "jp", "art19", "podcast", "episode", "tweet",
    "rss", "spotify", "apple", "itunes", "android", "patreon", "twitter", "x",
    "this", "that", "with", "from", "about", "more", "here", "click", "please",
}

# Katakana loanwords common enough that absence from a transcript means nothing.
_KATAKANA_STOPWORDS = {
    "エピソード", "ポッドキャスト", "プライバシー", "ポリシー", "スポンサー",
    "リスナー", "ハッシュタグ", "コメント", "サポート", "プラン", "トピック",
    "レポート", "ゲスト", "ホスト", "テーマ", "イベント", "サービス", "ユーザー",
    "プロダクト", "ビジネス", "デザイン", "エンジニア", "アプリケーション",
    "カンファレンス", "ネイティブ", "ローカル", "コンセプト", "アプローチ",
}

_PREAMBLE_PATTERNS = [
    r"^承知(いた)?しました",
    r"^かしこまりました",
    r"^了解(いた)?しました",
    r"^はい[、。]",
    r"^以下(に|の)",
    r"^もちろん(です)?[、。]",
    r"^喜んで",
    r"^Sure[,!]",
    r"^Certainly[,!]",
    r"^Of course[,!]",
    r"^Here('s| is| are)\b",
    r"^I'(ll|ve)\b",
    r"^As requested",
]

# A chapter title should be a label. These signal a raw transcript slice instead.
_FRAGMENT_SUFFIXES = (
    "て", "で", "が", "を", "に", "は", "も", "と", "の", "けど", "ので", "から",
    "たり", "みたいな", "という", "ですが", "ますが", "んですけど",
)


@dataclass
class Correction:
    """One suspected misrecognition: what the show notes say vs what Whisper wrote."""

    official: str
    transcript_form: Optional[str] = None
    confidence: str = "low"  # low | medium | high
    # "misrecognition" = Whisper heard it wrong and the text is misleading.
    # "script_variant" = same word, different script (Terminal / ターミナル). Not a defect.
    # "unconfirmed"    = absent from the transcript, nothing matched. Needs human eyes.
    kind: str = "misrecognition"
    # Surrounding transcript text, so a wrong pairing is obvious at a glance
    # rather than something the reader has to go hunting for.
    context: Optional[str] = None

    def as_line(self) -> str:
        if self.kind == "unconfirmed" or not self.transcript_form:
            return f"（転写に見当たらず・要目視） → {self.official}"
        if self.kind == "script_variant":
            return f"{self.transcript_form} ≒ {self.official}（表記ゆれ・実害なし）"
        return f"{self.transcript_form} → {self.official}"


@dataclass
class VerificationReport:
    """Everything the verification pass learned. Advisory only — nothing is auto-applied."""

    official_notes: Optional[str] = None
    notes_source: Optional[str] = None
    corrections: List[Correction] = field(default_factory=list)
    missing_terms: List[str] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    uncovered_topics: List[str] = field(default_factory=list)
    checked_terms: int = 0

    def by_kind(self, kind: str) -> List[Correction]:
        return [c for c in self.corrections if c.kind == kind]

    @property
    def misrecognitions(self) -> List[Correction]:
        """The ones that actually mislead a reader."""
        return self.by_kind("misrecognition")

    @property
    def has_findings(self) -> bool:
        return bool(self.corrections or self.quality_issues or self.uncovered_topics)

    def print_summary(self) -> None:
        print(f"   📖 公式ノート: {self.notes_source or '取得できず'}")
        print(f"   🔤 照合した固有名詞: {self.checked_terms}語")

        real = self.misrecognitions
        if real:
            print(f"   ⚠️  誤認（要訂正）: {len(real)}件")
            for c in real:
                print(f"      - {c.as_line()}  [{c.confidence}]")
                if c.context:
                    print(f"          文脈: {c.context}")
        else:
            print("   ✅ 実害のある誤認は検出されず")

        variants = self.by_kind("script_variant")
        if variants:
            print(f"   ℹ️  表記ゆれ（実害なし）: {len(variants)}件")
        unconfirmed = self.by_kind("unconfirmed")
        if unconfirmed:
            print(f"   ❓ 転写に見当たらない語: {len(unconfirmed)}件（要目視）")
            for c in unconfirmed:
                print(f"      - {c.official}")

        if self.quality_issues:
            print(f"   ⚠️  出力品質の問題: {len(self.quality_issues)}件")
            for issue in self.quality_issues:
                print(f"      - {issue}")
        else:
            print("   ✅ 出力品質チェック通過")

        if self.uncovered_topics:
            print(f"   ℹ️  要約が触れていない公式トピック: {len(self.uncovered_topics)}件")
            for t in self.uncovered_topics:
                print(f"      - {t}")

    def as_markdown(self) -> str:
        lines = ["## Verification", ""]
        lines.append(f"- 公式ノート取得元: {self.notes_source or '取得できず'}")
        lines.append(f"- 照合した固有名詞: {self.checked_terms}語")

        sections = [
            ("固有名詞の誤認（要訂正）", self.misrecognitions),
            ("転写に見当たらない語（要目視）", self.by_kind("unconfirmed")),
            ("表記ゆれ（実害なし）", self.by_kind("script_variant")),
        ]
        for heading, items in sections:
            if items:
                lines += ["", f"### {heading}", ""]
                for c in items:
                    lines.append(f"- {c.as_line()}（確度: {c.confidence}）")
                    if c.context:
                        lines.append(f"  - 文脈: {c.context}")

        if self.quality_issues:
            lines += ["", "### 出力品質の問題", ""]
            lines += [f"- {i}" for i in self.quality_issues]
        if self.uncovered_topics:
            lines += ["", "### 要約が触れていない公式トピック", ""]
            lines += [f"- {t}" for t in self.uncovered_topics]
        return "\n".join(lines) + "\n"


def _strip_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"</(p|li|div|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _context_snippet(transcript: str, form: str, window: int = 45) -> Optional[str]:
    """Text around the first occurrence of `form`, for at-a-glance judgement."""
    idx = transcript.find(form)
    if idx < 0:
        return None
    start, end = max(0, idx - window), min(len(transcript), idx + len(form) + window)
    snippet = transcript[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(transcript) else "")


def _is_script_swap(official: str, form: str) -> bool:
    """True when the two differ only by writing system (Terminal / ターミナル).

    Whisper writing a Latin technical term in katakana is a rendering choice, not
    a mishearing, so it must not be reported as something to correct.
    """
    ascii_only = re.fullmatch(r"[A-Za-z0-9 .+#/'-]+", official.strip())
    katakana_only = re.fullmatch(r"[ァ-ヴー・\s]+", form.strip())
    if ascii_only and katakana_only:
        return True
    return bool(re.fullmatch(r"[ァ-ヴー・\s]+", official.strip())
                and re.fullmatch(r"[A-Za-z0-9 .+#/'-]+", form.strip()))


def _normalize(text: str) -> str:
    """Fold away differences that should not count as a mismatch."""
    text = text.lower()
    text = text.replace("・", "").replace("･", "")
    text = re.sub(r"[\s　\-–—_.,/()（）「」『』:：]", "", text)
    return text


class TranscriptVerifier:
    """Checks a generated episode against its own show's published notes."""

    def __init__(self, gemini_generate: Optional[Callable[[str], Optional[str]]] = None):
        # Injected rather than imported so this module stays testable offline and
        # so the caller keeps control of Gemini rate limiting / quota accounting.
        self._gemini = gemini_generate
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "podcast-notes-automation/1.0"})

    # ---------------------------------------------------------------- notes

    def fetch_official_notes(
        self, show_name: str, episode_title: str, feed_url: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Return the show's own notes for this episode, via its RSS feed."""
        if not feed_url:
            feed_url = self._discover_feed_url(show_name)
        if not feed_url:
            return None

        try:
            resp = self._session.get(feed_url, timeout=60)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"   ⚠️  RSS取得/解析に失敗: {e}")
            return None

        channel = root.find("channel")
        if channel is None:
            return None

        best, best_score = None, 0.0
        for item in channel.findall("item"):
            title = item.findtext("title") or ""
            score = SequenceMatcher(None, _normalize(title), _normalize(episode_title)).ratio()
            if score > best_score:
                best_score, best = score, item

        if best is None or best_score < 0.6:
            print(f"   ⚠️  RSS内に該当エピソードが見つかりません (最高一致度 {best_score:.2f})")
            return None

        for tag in (CONTENT_ENCODED, "description", ITUNES_SUMMARY):
            raw = best.findtext(tag)
            if raw and raw.strip():
                return {
                    "notes": _strip_html(raw),
                    "source": f"{feed_url} ({tag.split('}')[-1]})",
                    "matched_title": best.findtext("title") or "",
                }
        return None

    def _discover_feed_url(self, show_name: str) -> Optional[str]:
        try:
            resp = self._session.get(
                "https://itunes.apple.com/search",
                params={"term": show_name, "media": "podcast", "entity": "podcast",
                        "limit": 10, "country": "jp"},
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except (requests.RequestException, ValueError):
            return None

        best, best_score = None, 0.0
        for r in results:
            score = max(
                SequenceMatcher(None, _normalize(show_name), _normalize(r.get("collectionName", ""))).ratio(),
                SequenceMatcher(None, _normalize(show_name), _normalize(r.get("artistName", ""))).ratio(),
            )
            if score > best_score:
                best_score, best = score, r
        return best.get("feedUrl") if best and best_score >= 0.5 else None

    # ---------------------------------------------------------------- terms

    def extract_terms(self, notes: str) -> List[str]:
        """Pull candidate proper nouns out of the official notes."""
        terms: List[str] = []

        # Multi-word Latin names: "AI Engineer World Fair", "Human in the loop".
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#./\-']*(?:\s+[A-Za-z0-9+#./\-']+)*", notes):
            phrase = m.group(0).strip()
            words = phrase.split()
            # Trim trailing lowercase filler so "Asterminds CTO の" style noise drops out.
            while words and words[-1].lower() in _TERM_STOPWORDS:
                words.pop()
            while words and words[0].lower() in _TERM_STOPWORDS:
                words.pop(0)
            if not words:
                continue
            phrase = " ".join(words)
            if len(phrase) < 3 or phrase.lower() in _TERM_STOPWORDS:
                continue
            # Drop URLs, bare domains and the privacy boilerplate every host appends.
            if phrase.startswith("http") or re.search(r"\.(com|jp|io|fm|net|org)\b", phrase, re.I):
                continue
            terms.append(phrase)

        # Katakana runs — product and concept names.
        for m in re.finditer(r"[ァ-ヴー]{4,}", notes):
            t = m.group(0)
            if t not in _KATAKANA_STOPWORDS:
                terms.append(t)

        # Person names introduced as 〇〇さん. The name body deliberately excludes
        # hiragana: `\w` matches Japanese too, so a looser class swallows the
        # particle and the preceding role ("Asterminds CTOのr.kagaya" as one name).
        for m in re.finditer(r"([A-Za-z][A-Za-z0-9._'-]{1,20}|[一-龥ァ-ヴー]{2,12})さん", notes):
            terms.append(m.group(1))

        # Dedupe, keep longest form when one contains another.
        uniq: List[str] = []
        for t in sorted(set(terms), key=len, reverse=True):
            if not any(_normalize(t) in _normalize(u) for u in uniq):
                uniq.append(t)
        return sorted(uniq, key=str.lower)

    def find_missing_terms(self, terms: List[str], transcript: str) -> List[str]:
        norm_transcript = _normalize(transcript)
        return [t for t in terms if _normalize(t) not in norm_transcript]

    # ------------------------------------------------------- self-consistency

    def check_output_quality(
        self,
        summary: Optional[str],
        key_takeaways: Optional[str],
        chapters: Optional[str],
    ) -> List[str]:
        """Deterministic checks encoding bugs this pipeline has actually shipped."""
        issues: List[str] = []

        if not summary or not summary.strip():
            issues.append("Summary が空です")
        else:
            first = summary.strip().splitlines()[0].strip()
            for pat in _PREAMBLE_PATTERNS:
                if re.search(pat, first):
                    issues.append(f"Summary の先頭にAIの前置きが混入している可能性: 「{first[:40]}」")
                    break
            length = len(summary.strip())
            if length < 80:
                issues.append(f"Summary が短すぎます（{length}文字）")
            elif length > 1200:
                issues.append(f"Summary が長すぎます（{length}文字）— 話題を絞れていない可能性")

        if not key_takeaways or not key_takeaways.strip():
            issues.append("Key Takeaways が空です")
        else:
            bullets = [l for l in key_takeaways.splitlines() if l.strip().startswith(("-", "*", "・"))]
            if len(bullets) < 3:
                issues.append(f"Key Takeaways の項目が少なすぎます（{len(bullets)}項目）")
            for b in bullets:
                for pat in _PREAMBLE_PATTERNS:
                    if re.search(pat, b.lstrip("-*・ ")):
                        issues.append(f"Key Takeaways にAIの前置きが混入: 「{b.strip()[:40]}」")
                        break

        if not chapters or not chapters.strip():
            issues.append("Timestamps が空です")
        else:
            for line in chapters.splitlines():
                m = re.match(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)$", line)
                if not m:
                    continue
                ts, title = m.group(1), m.group(2).strip()
                if not title:
                    issues.append(f"{ts} の章タイトルが空です")
                elif len(title) > 45:
                    issues.append(f"{ts} の章タイトルが長すぎます（転写断片の可能性）: 「{title[:40]}…」")
                elif title.endswith(_FRAGMENT_SUFFIXES):
                    issues.append(f"{ts} の章タイトルが文の途中で切れています: 「{title}」")
                elif title.count("。") >= 2:
                    issues.append(f"{ts} の章タイトルが文章になっています: 「{title[:40]}」")
        return issues

    def check_topic_coverage(self, topics: List[str], summary: str, key_takeaways: str) -> List[str]:
        """Official bullet topics that the generated notes never touch."""
        if not topics:
            return []
        haystack = _normalize((summary or "") + (key_takeaways or ""))
        uncovered = []
        for topic in topics:
            keywords = [w for w in re.findall(r"[A-Za-z]{4,}|[ァ-ヴー]{3,}|[一-龥]{2,}", topic)]
            if not keywords:
                continue
            if not any(_normalize(k) in haystack for k in keywords):
                uncovered.append(topic)
        return uncovered

    @staticmethod
    def extract_topics(notes: str) -> List[str]:
        """The bullet list most shows publish under 話したネタ / Topics."""
        lines = [l.strip() for l in notes.splitlines() if l.strip()]
        topics, capturing = [], False
        for line in lines:
            if re.match(r"^(話したネタ|話した内容|トピック|Topics?|Show ?notes?|目次)[:：]?$", line, re.I):
                capturing = True
                continue
            if capturing:
                if re.match(r"^(出演者|Tweet|購読|関連リンク|リンク|See Privacy|Sponsors?)\b", line, re.I):
                    break
                if line.startswith("http"):
                    continue
                topics.append(re.sub(r"^[-*・\d.]+\s*", "", line))
        return [t for t in topics if 4 <= len(t) <= 120]

    # ------------------------------------------------------------- gemini

    def suggest_corrections(
        self, missing_terms: List[str], transcript: str, max_chars: int = 60000
    ) -> List[Correction]:
        """Ask Gemini what the transcript wrote instead. At most one call."""
        if not missing_terms:
            return []
        unconfirmed = [Correction(official=t, confidence="low", kind="unconfirmed") for t in missing_terms]
        if not self._gemini:
            return unconfirmed

        excerpt = transcript[:max_chars]
        prompt = (
            "あなたは音声認識(Whisper)の誤認を検出する校正者です。\n"
            "以下は、ある番組の公式ショーノートに載っている正しい固有名詞のリストと、"
            "同じエピソードのWhisper自動転写です。\n"
            "各固有名詞について、転写の中でどう書かれているかを特定し分類してください。\n\n"
            "分類:\n"
            '- "misrecognition": 音を聞き間違えて別の語になっている（例: 加賀谷→香谷、Anthropic→Hansolpec）。読者が誤解する。\n'
            '- "script_variant": 同じ語だが表記が違うだけ（例: Terminal→ターミナル、Goal-based→ゴールベース）。実害なし。\n\n'
            "ルール:\n"
            "- 転写中に対応する箇所が見つかる場合のみ報告する。見つからない語はスキップ（推測で作らない）\n"
            "- 単なるカタカナ⇔英字の置き換えは必ず script_variant にする。misrecognition にしない\n"
            "- confidence は high / medium / low のいずれか\n"
            "- 出力はJSON配列のみ。説明文や前置きは一切書かない\n\n"
            '形式: [{"official":"正しい表記","transcript_form":"転写中の表記","kind":"misrecognition","confidence":"high"}]\n\n'
            f"【正しい固有名詞】\n{chr(10).join('- ' + t for t in missing_terms)}\n\n"
            f"【Whisper転写】\n{excerpt}"
        )

        raw = self._gemini(prompt)
        if not raw:
            return unconfirmed

        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return unconfirmed
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return unconfirmed

        corrections, named = [], set()
        for entry in data:
            if not isinstance(entry, dict):
                continue
            official = str(entry.get("official", "")).strip()
            form = str(entry.get("transcript_form", "")).strip()
            conf = str(entry.get("confidence", "low")).strip().lower()
            kind = str(entry.get("kind", "misrecognition")).strip().lower()
            if not official or not form or form == official:
                continue
            kind = kind if kind in {"misrecognition", "script_variant"} else "misrecognition"
            # Guard against a hallucinated pairing: the garbled form Gemini
            # reports must literally exist in the transcript.
            if form not in transcript:
                corrections.append(Correction(official=official, confidence="low", kind="unconfirmed"))
                named.add(official)
                continue
            # Gemini still occasionally calls a plain transliteration an error.
            # ASCII term rendered as katakana (or vice versa) is never a defect.
            if kind == "misrecognition" and _is_script_swap(official, form):
                kind = "script_variant"
            corrections.append(Correction(
                official=official,
                transcript_form=form,
                confidence=conf if conf in {"high", "medium", "low"} else "low",
                kind=kind,
                context=_context_snippet(transcript, form),
            ))
            named.add(official)

        # Terms Gemini could not place are still worth surfacing for human review.
        corrections += [c for c in unconfirmed if c.official not in named]
        # Real misrecognitions first — those are what a reader needs.
        order = {"misrecognition": 0, "unconfirmed": 1, "script_variant": 2}
        return sorted(corrections, key=lambda c: (order.get(c.kind, 3), c.official.lower()))

    # -------------------------------------------------------------- verify

    def verify(
        self,
        show_name: str,
        episode_title: str,
        transcript: str,
        summary: Optional[str] = None,
        key_takeaways: Optional[str] = None,
        chapters: Optional[str] = None,
        feed_url: Optional[str] = None,
    ) -> VerificationReport:
        report = VerificationReport()
        report.quality_issues = self.check_output_quality(summary, key_takeaways, chapters)

        fetched = self.fetch_official_notes(show_name, episode_title, feed_url)
        if not fetched:
            return report

        report.official_notes = fetched["notes"]
        report.notes_source = fetched["source"]
        report.topics = self.extract_topics(fetched["notes"])

        terms = self.extract_terms(fetched["notes"])
        report.checked_terms = len(terms)
        report.missing_terms = self.find_missing_terms(terms, transcript)
        report.corrections = self.suggest_corrections(report.missing_terms, transcript)
        report.uncovered_topics = self.check_topic_coverage(
            report.topics, summary or "", key_takeaways or ""
        )
        return report
