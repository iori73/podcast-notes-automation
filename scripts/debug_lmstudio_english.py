#!/usr/bin/env python3
"""
Diagnose why the LM Studio run on the Jenny Wen (English) episode dropped
"Legibility Framework" / "Claude Co-work" while Gemini's run kept them.

Checks, in order:
1. Does process_unified.py's own chunk cap (max 6 of N chunks, sampled from
   start/middle/end) drop the chunk containing "legibility" before any LLM
   ever sees it? If so this is a pipeline bug, not a local-model weakness.
2. If the chunk survives the cap, does the CURRENT chunk-summary prompt
   preserve the mention? Compare against a prompt that explicitly calls out
   product/framework names as a category to extract.
"""

import re
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODEL = "google/gemma-4-e4b"

EPISODE_FILE = Path("data/outputs/The design process is dead. Here’s what’s replacing it. | Jenny Wen (head of design at Claude)/episode_summary.md")


def lm_generate(prompt: str, max_tokens: int = 1024) -> str:
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        LM_STUDIO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def split_text(text, max_chars):
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


content = EPISODE_FILE.read_text(encoding="utf-8")
m = re.search(r"## Transcript\s*\n+(.*)", content, re.S)
transcript = m.group(1).strip()
print(f"Transcript chars: {len(transcript)}")

pos = transcript.lower().find("legibility framework")
print(f"'legibility framework' char offset in transcript: {pos}")

all_chunks = split_text(transcript, max_chars=8000)
print(f"Raw chunk count (before the >6 cap): {len(all_chunks)}")

target_idx = None
for i, c in enumerate(all_chunks):
    if "legibility" in c.lower():
        target_idx = i
        print(f"  -> found in raw chunk index {i} (0-based) of {len(all_chunks)}")

if len(all_chunks) > 6:
    mid = len(all_chunks) // 2
    selected_idx = list(range(0, 2)) + list(range(mid, mid + 2)) + list(range(len(all_chunks) - 2, len(all_chunks)))
    print(f"Selected chunk indices under the current >6-chunk cap: {selected_idx}")
    if target_idx is not None:
        print(f"Is the legibility chunk (idx {target_idx}) among the selected ones? {target_idx in selected_idx}")
else:
    print("No cap applied (<=6 chunks) — all chunks reach the LLM.")

if target_idx is not None:
    print("\n--- Testing whether the CURRENT chunk-summary prompt preserves the mention ---")
    chunk = all_chunks[target_idx]
    current_prompt = f"""
Summarize the key points of this podcast transcript excerpt in English.

Conditions:
- Up to 5 bullet points covering the key points
- Include proper nouns/keywords where present
- No preamble or self-reference

Podcast: The design process is dead
Episode: Jenny Wen episode

Transcript excerpt ({target_idx + 1}/{len(all_chunks)}):
{chunk}

Output:
- ...
""".strip()
    out = lm_generate(current_prompt)
    print("CURRENT prompt chunk-summary output:")
    print(out)
    print(f"\n'legibility' present in output? {'legibility' in out.lower()}")

    print("\n--- Testing a STRENGTHENED prompt that calls out named entities explicitly ---")
    strengthened_prompt = f"""
Summarize the key points of this podcast transcript excerpt in English.

Conditions:
- Up to 5 bullet points covering the key points
- CRITICAL: if the speaker names a specific framework, product, tool, or coined term (e.g. "the Legibility Framework", "Claude Co-work"), you MUST quote that exact name verbatim in a bullet — do not paraphrase or drop it, even if it seems minor relative to the rest of the excerpt
- No preamble or self-reference

Podcast: The design process is dead
Episode: Jenny Wen episode

Transcript excerpt ({target_idx + 1}/{len(all_chunks)}):
{chunk}

Output:
- ...
""".strip()
    out2 = lm_generate(strengthened_prompt)
    print("STRENGTHENED prompt chunk-summary output:")
    print(out2)
    print(f"\n'legibility' present in output? {'legibility' in out2.lower()}")
