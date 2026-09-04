#!/usr/bin/env python3
"""
One-episode quality test: local LM Studio model vs. the Gemini output already
saved for that episode.

Reuses the *exact* prompts from process_unified.py's
_generate_summary_and_timestamps / _classify_category, but sends them to a
local LM Studio server (OpenAI-compatible /v1/chat/completions) instead of
Gemini. Does not touch process_unified.py or upload anything to Notion —
this is a throwaway comparison to decide whether local-LLM migration is
worth pursuing.

Usage:
    python scripts/test_lmstudio_quality.py <episode_dir_name> <show_name> [--lang en]

    <episode_dir_name> is the folder name under data/outputs/ (must already
    contain an episode_summary.md from a prior Gemini run, used both as the
    transcript source and as the quality baseline to compare against).
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from philosophy import load_philosophy  # noqa: E402

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODEL = "google/gemma-4-e4b"

_args = argparse.ArgumentParser()
_args.add_argument("episode_dir")
_args.add_argument("show_name")
_args.add_argument("--lang", choices=["ja", "en"], default="ja")
_args.add_argument("--no-chunk-cap", action="store_true",
                    help="Feed every chunk to the LLM instead of process_unified.py's "
                         "start/middle/end 6-chunk sample (diagnostic: that cap silently "
                         "drops the middle of long transcripts before any LLM sees them).")
_parsed = _args.parse_args()

EPISODE_DIR = Path("data/outputs") / _parsed.episode_dir
EPISODE_FILE = EPISODE_DIR / "episode_summary.md"
SHOW_NAME = _parsed.show_name
EPISODE_TITLE = _parsed.episode_dir
LANGUAGE = _parsed.lang


def lm_generate(prompt: str, max_tokens: int = 4096, temperature: float = 0.7) -> Optional[str]:
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        LM_STUDIO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ LM Studio error: {e}")
        return None


def split_text(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    buf = ""
    for part in re.split(r"(\n+|。|！|？)", text):
        if not part:
            continue
        if len(buf) + len(part) <= max_chars:
            buf += part
            continue
        if buf.strip():
            chunks.append(buf.strip())
        buf = part
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def to_seconds(ts: str) -> int:
    try:
        mm, ss = ts.split(":")
        return int(mm) * 60 + int(ss)
    except Exception:
        return 0


def format_mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def build_chapter_context(timestamps_raw: List[Tuple[str, str]], interval_sec: int = 300, max_items: int = 14):
    if not timestamps_raw:
        return []
    buckets = {}
    for ts, text in timestamps_raw:
        bucket = (to_seconds(ts) // interval_sec) * interval_sec
        buckets.setdefault(bucket, [])
        if text:
            buckets[bucket].append(text.strip())
    items = []
    for bucket in sorted(buckets.keys()):
        combined = re.sub(r"\s+", " ", " ".join(buckets[bucket])).strip()
        if len(combined) > 220:
            combined = combined[:217] + "..."
        items.append((format_mmss(bucket), combined))
    if items and items[0][0] != "00:00":
        items.insert(0, ("00:00", items[0][1]))
    if len(items) <= max_items:
        return items
    step = max(1, len(items) // max_items)
    picked = items[::step][:max_items]
    if picked[-1] != items[-1] and len(picked) < max_items:
        picked.append(items[-1])
    return picked[:max_items]


def split_takeaways_and_note(text: str):
    pattern = r'\n[ \t]*(?:[-*・#>]+[ \t]*)?(?:\*\*|__)?\s*編集メモ\s*(?:\*\*|__)?\s*[:：]?[ \t]*\n?'
    parts = re.split(pattern, text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip() or None
    return text.strip(), None


def load_transcript_and_timestamps():
    """Extract the Transcript section from the already-processed episode file.

    The saved file interleaves prose (no per-line timestamps once written to
    markdown), so timestamps_raw is reconstructed as evenly-spaced buckets
    across the transcript length -- close enough for a chapter-title test,
    since the real pipeline's chapter prompt only sees ~300s-bucketed snippets
    anyway.
    """
    content = EPISODE_FILE.read_text(encoding="utf-8")
    m = re.search(r"## Transcript\s*\n+(.*)", content, re.S)
    transcript = m.group(1).strip() if m else ""
    paras = [p.strip() for p in transcript.split("\n\n") if p.strip()]
    timestamps_raw = []
    for i, p in enumerate(paras):
        timestamps_raw.append((format_mmss(i * 60), p))
    return transcript, timestamps_raw


def extract_gemini_sections(content: str):
    def section(name, stop_names):
        pat = rf"## {name}\s*\n+(.*?)(?=\n## (?:{'|'.join(stop_names)})|\Z)"
        m = re.search(pat, content, re.S)
        return m.group(1).strip() if m else ""

    return {
        "summary": section("Summary", ["Key Takeaways", "Timestamps", "Transcript"]),
        "key_takeaways": section("Key Takeaways", ["Timestamps", "Transcript"]),
        "timestamps": section("Timestamps", ["Transcript"]),
    }


def main():
    print("=" * 60)
    print(f"LM Studio quality test — {LM_STUDIO_MODEL}")
    print(f"Episode: {EPISODE_TITLE}")
    print("=" * 60)

    transcript, timestamps_raw = load_transcript_and_timestamps()
    print(f"Transcript chars: {len(transcript)}")

    lang = "日本語" if LANGUAGE == "ja" else "English"
    philosophy = load_philosophy(SHOW_NAME)
    philosophy_block = f"\n【編集方針（この思想のもとで書く）】\n{philosophy}\n".rstrip() if philosophy else ""
    print(f"Philosophy loaded: {len(philosophy)} chars")

    chunks = split_text(transcript, max_chars=8000)
    raw_chunk_count = len(chunks)
    if len(chunks) > 6 and not _parsed.no_chunk_cap:
        mid = len(chunks) // 2
        chunks = chunks[:2] + chunks[mid:mid + 2] + chunks[-2:]
    print(f"Chunks: {len(chunks)} (of {raw_chunk_count} raw{' — CAP DISABLED' if _parsed.no_chunk_cap else ''})")

    chunk_summaries = []
    for idx, chunk in enumerate(chunks, start=1):
        prompt = f"""
あなたは優秀な編集者です。次のポッドキャスト文字起こし（断片）を{lang}で要点整理してください。

条件:
- 断片の要点を箇条書きで5個まで
- 固有名詞/キーワードがあれば含める
- 余計な前置きや自己言及は禁止

番組: {SHOW_NAME}
回: {EPISODE_TITLE}

文字起こし（断片 {idx}/{len(chunks)}）:
{chunk}

出力:
- ...
""".strip()
        out = lm_generate(prompt)
        print(f"  chunk {idx}/{len(chunks)}: {'ok' if out else 'FAILED'} ({len(out) if out else 0} chars)")
        if out:
            chunk_summaries.append(out)

    final_prompt = f"""
あなたは優秀な編集者です。以下はポッドキャストの要点メモ（複数断片のまとめ）です。
これを元に、{lang}で「Summary」と「Key Takeaways」を作成してください。
{philosophy_block}

【Summaryの条件】
- 250〜450文字程度（英語の場合は600〜900 characters程度）
- エピソードで実際に議論・紹介された内容を具体的に要約する
- タイトルをそのまま言い換えるだけの要約は禁止
- 番組の定型紹介文（「〜という番組です」など）を含めるのは禁止
- ゲスト紹介だけで終わる要約は禁止
- 「このエピソードでは〜について話されています」という書き方は禁止
- 具体的に何が語られたか、どんな主張・知見・事例・データが紹介されたかを書く
- 内容の推測はせず、与えられた情報の範囲で
- 文字数を超えそうなときは、具体（数字・固有名詞・事例）を削るのではなく扱う話題を絞る
- LaTeX記法や数式記号（$\rightarrow$ など）は使わない。矢印は→、その他の記号も普通の文章として書く
- 要点メモの中に固有名詞（フレームワーク名・製品名・造語）が一度でも出てきたら、それが全体の中で目立たなくても、必ずどこかに残す。頻出テーマだけを拾って一度しか出ない具体名を切り捨てるのは禁止

【Key Takeawaysの条件】
- 箇条書きで3〜5点
- このエピソード固有の学び・気づき・主張を書く
- 「〜について学べます」などの抽象的な表現は禁止
- 具体的な数字・事例・人名・概念名を含める
- LaTeX記法や数式記号は使わない
- 要点メモに登場した固有名詞（フレームワーク名・製品名など）は一度でも出てきたら最低1点はそれに触れる項目を作る

番組: {SHOW_NAME}
回: {EPISODE_TITLE}

要点メモ:
{chr(10).join(chunk_summaries) if chunk_summaries else transcript[:12000]}

出力形式（この順番で、見出し行も含めて出力）:
Summary:
...

Key Takeaways:
- ...

編集メモ:
核となる問い: （このエピソードが本当は何を巡って話しているか。1行）
取捨の理由: （何を中心に据え、何を落としたか。1〜2行）
""".strip()

    final = lm_generate(final_prompt, temperature=0.3)
    summary, key_takeaways, editor_note = None, None, None
    if final:
        # LM Studio decorates the label with markdown bold, and inconsistently
        # puts the closing ** before OR after the colon ("**X:**" or "**X**:") —
        # both orders must match, unlike Gemini which never decorates.
        parts = re.split(r'(?:\*\*|__)?\s*Key Takeaways\s*(?:\*\*|__)?\s*[:：]\s*(?:\*\*|__)?\s*\n', final, maxsplit=1)
        if len(parts) == 2:
            summary_part = parts[0]
            m = re.search(r'(?:\*\*|__)?\s*Summary\s*(?:\*\*|__)?\s*[:：]\s*(?:\*\*|__)?\s*\n?', summary_part)
            if m:
                summary_part = summary_part[m.end():]
            summary = summary_part.strip()
            key_takeaways, editor_note = split_takeaways_and_note(parts[1])
        else:
            summary = final.strip()

    chapter_items = build_chapter_context(timestamps_raw)
    chapter_context = "\n".join(f"{ts} {snippet}" for ts, snippet in chapter_items if snippet)
    chapter_prompt = f"""
あなたはポッドキャストの編集者です。以下の時刻ごとの内容メモから、章タイトル（チャプター目次）を作ってください。

条件:
- 各行の時刻（MM:SS）はそのまま維持（変更しない）
- 時刻の後に、内容を表す短いタイトルを付ける（{lang}で 15〜30文字程度）
- 出力は「MM:SS タイトル」のみ（余計な説明は禁止）

番組: {SHOW_NAME}
回: {EPISODE_TITLE}

内容メモ:
{chapter_context}

出力:
""".strip()
    chapters = lm_generate(chapter_prompt)

    safe_name = re.sub(r'[^\w\-#]+', '_', _parsed.episode_dir)[:60]

    out_dir = Path("data/outputs") / "_lmstudio_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_name}_lmstudio_output.md"
    out_path.write_text(
        f"""## Summary (LM Studio: {LM_STUDIO_MODEL})

{summary or '(FAILED)'}

## Key Takeaways

{key_takeaways or '(FAILED)'}

## Timestamps

{chapters or '(FAILED)'}

## 編集メモ (raw model reasoning, not published normally)

{editor_note or '(none)'}
""",
        encoding="utf-8",
    )
    print(f"\n✅ Saved LM Studio output to: {out_path}")

    gemini = extract_gemini_sections(EPISODE_FILE.read_text(encoding="utf-8"))
    compare_path = out_dir / f"{safe_name}_comparison.md"
    compare_path.write_text(
        f"""# Comparison: Gemini (already published) vs. LM Studio ({LM_STUDIO_MODEL})

## Summary

### Gemini
{gemini['summary']}

### LM Studio
{summary or '(FAILED)'}

## Key Takeaways

### Gemini
{gemini['key_takeaways']}

### LM Studio
{key_takeaways or '(FAILED)'}

## Timestamps

### Gemini
{gemini['timestamps']}

### LM Studio
{chapters or '(FAILED)'}
""",
        encoding="utf-8",
    )
    print(f"✅ Saved side-by-side comparison to: {compare_path}")


if __name__ == "__main__":
    main()
