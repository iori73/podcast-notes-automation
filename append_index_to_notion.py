"""
既存のNotionページの末尾に、index_supplement.md の内容を追記する。

対応するMarkdown要素:
- ## / ### / #### (見出し2/3、####はboldパラグラフ)
- 段落（インラインの [text](url) / **bold** / *italic* を解釈）
- - で始まる箇条書き（インライン書式同上）
- > で始まる引用（quoteブロック）
- --- で区切り線（dividerブロック）
"""

from __future__ import annotations
import re
import sys
import time
from pathlib import Path

import requests
import yaml


CONFIG_PATH = Path(__file__).parent / "config" / "config.yaml"


def load_notion_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    api_key = cfg["notion"]["api_key"]
    return api_key


def hyphenate(page_id: str) -> str:
    s = page_id.replace("-", "")
    return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"


# ---------- Markdown → Notion blocks ----------

# Inline tokens: [text](url) / **bold** / *italic*
INLINE_PATTERNS = [
    ("link", re.compile(r"\[([^\]]+)\]\(([^)]+)\)")),
    ("bold", re.compile(r"\*\*([^*]+)\*\*")),
    ("italic", re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")),
]


def parse_inline(text: str) -> list[dict]:
    """Return Notion rich_text array for a single inline string."""
    if not text:
        return []

    # Tokenize
    tokens: list[tuple[str, str, str | None]] = []  # (kind, content, url)
    i = 0
    while i < len(text):
        # find earliest match among patterns
        best = None
        for kind, pat in INLINE_PATTERNS:
            m = pat.search(text, i)
            if m and (best is None or m.start() < best[1].start()):
                best = (kind, m)
        if best is None:
            tokens.append(("plain", text[i:], None))
            break
        kind, m = best
        if m.start() > i:
            tokens.append(("plain", text[i:m.start()], None))
        if kind == "link":
            tokens.append(("link", m.group(1), m.group(2)))
        elif kind == "bold":
            tokens.append(("bold", m.group(1), None))
        elif kind == "italic":
            tokens.append(("italic", m.group(1), None))
        i = m.end()

    rich = []
    for kind, content, url in tokens:
        if not content:
            continue
        item = {"type": "text", "text": {"content": content}}
        annotations = {}
        if kind == "link":
            item["text"]["link"] = {"url": url}
        elif kind == "bold":
            annotations["bold"] = True
        elif kind == "italic":
            annotations["italic"] = True
        if annotations:
            item["annotations"] = annotations
        rich.append(item)
    return rich


def md_to_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    lines = md.splitlines()

    paragraph_buf: list[str] = []

    def flush_paragraph():
        nonlocal paragraph_buf
        if not paragraph_buf:
            return
        text = " ".join(s.strip() for s in paragraph_buf if s.strip())
        paragraph_buf = []
        if not text:
            return
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": parse_inline(text)},
        })

    for raw in lines:
        line = raw.rstrip()

        if not line.strip():
            flush_paragraph()
            continue

        if line.strip() == "---":
            flush_paragraph()
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        if line.startswith("#### "):
            flush_paragraph()
            content = line[5:].strip()
            rich = parse_inline(content)
            # Make the entire heading bold
            for r in rich:
                ann = r.setdefault("annotations", {})
                ann["bold"] = True
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich},
            })
            continue

        if line.startswith("### "):
            flush_paragraph()
            content = line[4:].strip()
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": parse_inline(content)},
            })
            continue

        if line.startswith("## "):
            flush_paragraph()
            content = line[3:].strip()
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": parse_inline(content)},
            })
            continue

        if line.startswith("> "):
            flush_paragraph()
            content = line[2:].strip()
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": parse_inline(content)},
            })
            continue

        if line.lstrip().startswith("- "):
            flush_paragraph()
            content = line.lstrip()[2:].strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_inline(content)},
            })
            continue

        # default: paragraph (collect contiguous lines)
        paragraph_buf.append(line)

    flush_paragraph()
    return blocks


# ---------- Notion API ----------

def append_blocks(page_id: str, blocks: list[dict], api_key: str) -> bool:
    url = f"https://api.notion.com/v1/blocks/{hyphenate(page_id)}/children"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    BATCH = 100
    for i in range(0, len(blocks), BATCH):
        batch = blocks[i:i + BATCH]
        resp = requests.patch(url, headers=headers, json={"children": batch})
        if resp.status_code != 200:
            print(f"❌ append failed batch {i//BATCH+1}: {resp.status_code}")
            print(resp.text[:800])
            return False
        print(f"   ✅ {i+1}〜{min(i+BATCH, len(blocks))} / {len(blocks)} 追加完了")
        time.sleep(0.2)
    return True


# ---------- Main ----------

TASKS = [
    {
        "name": "前編",
        "page_id": "355264826e0c81ad848dcbea91d03e2e",
        "md_path": Path(
            "data/outputs/あるべき未来を取り戻す 前編｜Talk with ： 牧大介（エーゼログループ 代表）/index_supplement.md"
        ),
    },
    {
        "name": "後編",
        "page_id": "355264826e0c81aaab47c077819f05c0",
        "md_path": Path(
            "data/outputs/あるべき未来を取り戻す 後編｜Talk with ： 牧大介（エーゼログループ 代表）/index_supplement.md"
        ),
    },
]


def main():
    api_key = load_notion_config()

    only = sys.argv[1] if len(sys.argv) > 1 else None

    for task in TASKS:
        if only and task["name"] != only:
            continue
        md = task["md_path"].read_text(encoding="utf-8")
        blocks = md_to_blocks(md)
        print(f"\n=== {task['name']} ({task['page_id']}) — {len(blocks)} blocks ===")
        ok = append_blocks(task["page_id"], blocks, api_key)
        print(f"{'✅ done' if ok else '❌ failed'}: {task['name']}")


if __name__ == "__main__":
    main()
