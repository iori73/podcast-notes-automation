#!/usr/bin/env python3
"""Answer a question across every episode note, instead of one episode at a time.

Why this exists
---------------
The pipeline produces one page per episode: Summary, Key Takeaways, Timestamps,
Transcript. That shape is inherited from paper notebooks — it stores what was
said, filed by where it was said. But the moments these notes actually paid off
were the cross-episode ones: reading #385 and #25 together to extract a
methodology, or asking "what should I apply from this?" and having to re-read
several transcripts by hand to answer it.

This script makes the question the unit of work and demotes episode pages to
source material. Retrieval is deliberately dumb — local term overlap, no
embeddings, no extra dependencies, no API cost — because with fewer than a few
hundred episodes it is good enough, and it keeps the whole thing runnable offline
right up to the single synthesis call.

Usage:
    python scripts/ask_across_episodes.py "ループ設計について各エピソードは何と言っているか"
    python scripts/ask_across_episodes.py "デザインシステムとAI" --top 8 --show Automagic
    python scripts/ask_across_episodes.py "検証をどう自動化するか" --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # process_unified.py lives at the repo root
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "src" / "integrations"))

OUTPUTS_DIR = REPO_ROOT / "data" / "outputs"
CROSS_DIR = REPO_ROOT / "data" / "cross"

# Terms too generic to discriminate between episodes.
_QUERY_STOPWORDS = {
    "こと", "もの", "ため", "とき", "ところ", "よう", "それ", "これ", "など",
    "して", "する", "した", "ある", "いる", "なる", "思う", "話", "回", "各",
    "エピソード", "ポッドキャスト", "について", "という", "どう", "何",
    "the", "and", "for", "with", "that", "this", "what", "how", "are", "was",
}


@dataclass
class EpisodeNote:
    """One episode's generated note, parsed into its sections."""

    path: Path
    title: str
    summary: str = ""
    key_takeaways: str = ""
    transcript: str = ""
    show: str = ""
    score: float = 0.0
    hits: Dict[str, int] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        """Summary + Key Takeaways — the part worth scoring heavily."""
        return f"{self.summary}\n{self.key_takeaways}"


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def extract_query_terms(question: str) -> List[str]:
    """Pull discriminating terms out of the question.

    Japanese needs no real tokenizer here: katakana runs, kanji runs and Latin
    words are exactly the content-bearing pieces, and particles fall away on their
    own because they are hiragana.
    """
    q = _normalize(question)
    terms: List[str] = []
    # Two-letter Latin acronyms carry a lot of weight in this corpus (AI, UX, ML,
    # VC), so the minimum length is 2 rather than 3.
    terms += re.findall(r"[a-z][a-z0-9.+#\-]{1,}", q)
    terms += re.findall(r"[ァ-ヴー]{3,}", question)
    terms += re.findall(r"[一-龥]{2,}", question)
    seen, out = set(), []
    for t in terms:
        tn = _normalize(t)
        if tn in _QUERY_STOPWORDS or len(tn) < 2 or tn in seen:
            continue
        seen.add(tn)
        out.append(t)
    return out


def load_notes(outputs_dir: Path = OUTPUTS_DIR, show_filter: Optional[str] = None) -> List[EpisodeNote]:
    """Parse every episode_summary.md under data/outputs/."""
    notes: List[EpisodeNote] = []
    if not outputs_dir.exists():
        return notes

    for md in sorted(outputs_dir.glob("*/episode_summary.md")):
        try:
            raw = md.read_text(encoding="utf-8")
        except OSError:
            continue

        note = EpisodeNote(path=md, title=md.parent.name)

        def section(name: str, nxt: str) -> str:
            m = re.search(rf"^## {name}\s*$\n(.*?)(?=^## {nxt}\s*$)", raw, re.S | re.M)
            return m.group(1).strip() if m else ""

        note.summary = section("Summary", "Key Takeaways") or section("Summary", "Timestamps")
        note.key_takeaways = section("Key Takeaways", "Timestamps")
        parts = raw.split("## Transcript", 1)
        note.transcript = parts[1].strip() if len(parts) == 2 else ""

        if show_filter and _normalize(show_filter) not in _normalize(note.title):
            continue
        notes.append(note)
    return notes


def score_notes(notes: List[EpisodeNote], terms: List[str]) -> List[EpisodeNote]:
    """Rank by term overlap, weighting the curated sections above raw transcript.

    A term appearing in the Summary means the episode is *about* it; the same term
    buried once in a transcript usually means it was mentioned in passing.
    """
    for note in notes:
        digest_n = _normalize(note.digest)
        title_n = _normalize(note.title)
        transcript_n = _normalize(note.transcript)
        total, hits = 0.0, {}
        for term in terms:
            t = _normalize(term)
            in_title = title_n.count(t)
            in_digest = digest_n.count(t)
            in_transcript = transcript_n.count(t)
            if not (in_title or in_digest or in_transcript):
                continue
            hits[term] = in_digest + in_transcript + in_title
            # Diminishing returns on repetition so one chatty episode cannot
            # dominate purely by saying a word forty times.
            total += 6.0 * in_title + 4.0 * in_digest + min(in_transcript, 8) * 0.5

        # Weight by how many *distinct* query terms matched. A single ambiguous
        # word repeated often ("エージェント" meaning a literary agent) otherwise
        # outranks an episode that actually covers the whole question.
        coverage = len(hits) / len(terms) if terms else 0.0
        note.score = total * (0.4 + 0.6 * coverage)
        note.hits = hits
    return sorted(notes, key=lambda n: n.score, reverse=True)


def extract_passages(note: EpisodeNote, terms: List[str], window: int = 320, limit: int = 3) -> List[str]:
    """Transcript neighbourhoods around the matched terms, for grounding."""
    transcript = note.transcript
    if not transcript:
        return []
    t_norm = _normalize(transcript)
    spans: List[Tuple[int, int]] = []
    for term in terms:
        t = _normalize(term)
        start = 0
        while len(spans) < limit * 3:
            idx = t_norm.find(t, start)
            if idx < 0:
                break
            spans.append((max(0, idx - window), min(len(transcript), idx + window)))
            start = idx + max(len(t), 1)

    if not spans:
        return []
    spans.sort()
    merged: List[List[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    return [re.sub(r"\s+", " ", transcript[s:e]).strip() for s, e in merged[:limit]]


def build_prompt(question: str, selected: List[EpisodeNote], terms: List[str]) -> str:
    blocks = []
    for i, note in enumerate(selected, start=1):
        passages = extract_passages(note, terms)
        block = [f"### 資料{i}: {note.title}"]
        if note.summary:
            block.append(f"[要約] {note.summary}")
        if note.key_takeaways:
            block.append(f"[要点] {note.key_takeaways}")
        for p in passages:
            block.append(f"[転写抜粋] …{p}…")
        blocks.append("\n".join(block))

    try:
        from philosophy import load_philosophy
        philosophy = load_philosophy()
    except Exception:
        philosophy = ""

    philosophy_block = f"\n【編集方針】\n{philosophy}\n" if philosophy else ""

    return f"""
あなたは複数のポッドキャストを横断して読む編集者です。
以下の資料は、別々のエピソードから取り出した要約・要点・転写抜粋です。
これらを横断して、一つの問いに答えてください。
{philosophy_block}
【問い】
{question}

【答え方】
- エピソードごとの要約を並べるのではなく、問いに対する一つの答えとして構成する
- 各主張の直後に、根拠となったエピソード名を「（出典: エピソード名）」の形で必ず示す
- 資料間で見解が異なる場合は、揃えずに「ここは割れている」と明示して両方書く
- 資料に書かれていないことは書かない。推測が必要な部分は「資料からは判断できない」と書く
- 最後に「未解決の問い」として、資料では答えが出ていない点を2〜3個挙げる
- 前置きや自己言及は書かない。本文から始める

【出力形式】
## 答え
（本文。見出しを使って構造化してよい）

## 見解が割れている点
- ...

## 未解決の問い
- ...

【資料】
{chr(10).join(blocks)}
""".strip()


def slugify(question: str, max_len: int = 60) -> str:
    s = re.sub(r"\s+", "_", question.strip())
    s = re.sub(r"[^\w぀-ヿ一-鿿_-]", "", s)
    return s[:max_len] or "question"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer one question across all episode notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
    python scripts/ask_across_episodes.py "ループ設計について各エピソードは何と言っているか"
    python scripts/ask_across_episodes.py "デザインシステムとAI" --top 8
    python scripts/ask_across_episodes.py "検証の自動化" --dry-run   # Geminiを呼ばず候補だけ表示
        """,
    )
    parser.add_argument("question", help="横断して問いたいこと")
    parser.add_argument("--top", type=int, default=6, help="使用するエピソード数 (default: 6)")
    parser.add_argument("--show", type=str, help="番組名で絞り込む（部分一致）")
    parser.add_argument("--dry-run", action="store_true", help="Geminiを呼ばず、選ばれたエピソードだけ表示")
    parser.add_argument("--extra-terms", type=str, help="検索語を追加（カンマ区切り）")
    args = parser.parse_args()

    terms = extract_query_terms(args.question)
    if args.extra_terms:
        terms += [t.strip() for t in args.extra_terms.split(",") if t.strip()]
    if not terms:
        print("❌ 問いから検索語を抽出できませんでした。--extra-terms で指定してください。")
        return 1

    print(f"🔍 検索語: {', '.join(terms)}")

    notes = load_notes(show_filter=args.show)
    print(f"📚 対象エピソード: {len(notes)}件")
    if not notes:
        print("❌ data/outputs/ にエピソードが見つかりません。")
        return 1

    ranked = [n for n in score_notes(notes, terms) if n.score > 0]
    if not ranked:
        print("❌ 該当するエピソードがありません。別の語で試してください。")
        return 1

    selected = ranked[:args.top]
    print(f"\n📌 選ばれたエピソード（{len(selected)}件 / 該当{len(ranked)}件）:")
    for n in selected:
        matched = ", ".join(sorted(n.hits, key=lambda k: -n.hits[k])[:5])
        print(f"   {n.score:6.1f}  {n.title[:52]}")
        print(f"           ヒット語: {matched}")

    if len(ranked) > len(selected):
        print(f"\n   ℹ️  上位{len(selected)}件のみ使用（残り{len(ranked) - len(selected)}件は未使用）"
              f" — 増やすには --top {min(len(ranked), args.top + 4)}")

    prompt = build_prompt(args.question, selected, terms)

    if args.dry_run:
        print(f"\n--dry-run のためGeminiは呼びません（プロンプト {len(prompt)}文字）")
        return 0

    from process_unified import UnifiedProcessor
    processor = UnifiedProcessor.__new__(UnifiedProcessor)
    processor._init_gemini()
    if not processor.gemini_client:
        print("❌ Geminiが利用できません。--dry-run で候補確認のみ可能です。")
        return 1

    print("\n🧠 横断合成中...")
    answer = processor._gemini_generate(prompt)
    if not answer:
        print("❌ 生成に失敗しました（quota切れの可能性）。時間をおいて再実行してください。")
        return 1

    CROSS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CROSS_DIR / f"{datetime.now():%Y%m%d}_{slugify(args.question)}.md"
    body = [
        f"# {args.question}",
        "",
        f"_生成: {datetime.now():%Y-%m-%d %H:%M} / 検索語: {', '.join(terms)}_",
        "",
        "## 参照したエピソード",
        "",
    ]
    body += [f"- {n.title}（スコア {n.score:.1f}）" for n in selected]
    body += ["", "---", "", answer.strip(), ""]
    out_path.write_text("\n".join(body), encoding="utf-8")

    print(f"\n✅ 保存しました: {out_path}")
    print("\n" + "=" * 70)
    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
