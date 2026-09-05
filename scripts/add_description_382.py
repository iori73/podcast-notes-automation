#!/usr/bin/env python3
"""Prepend the Spotify show-notes description to episode #382's Notion page."""

import sys
import requests

sys.path.insert(0, 'src')
sys.path.insert(0, 'src/integrations')

from integrations.notion_client import NotionClient

PAGE_ID = "358264826e0c81798a4fc244065c91ce"

DESCRIPTION = (
    "デザインシステムの役割が、AIに「正しい部品を選ばせる」アプローチだけでなく、"
    "「ふさわしい判断をさせる」ための思想を渡す器への道筋も見え始めてきました。"
    "仕様ではなく意図を記述することで、見た目の一貫性ではなく意図の一貫性を明文化する。"
    "AI時代のデザインシステムは何を担うものなのか、その問い直しを試みてみたソロ回です。"
)

LINKS = [
    ("Pencil: Design on canvas. Land in code.", "https://www.pencil.dev/"),
    ("Agentic Design Systems in 2026 with Brad Frost", "https://www.youtube.com/watch?v=Vg78K3t9KYc"),
    ("Design Systems are now Inference Systems", "https://www.proofofconcept.pub/p/design-systems-are-now-inference"),
    ("AIにルールではなく視点を渡す Decision DNA", "https://yasuhisa.com/could/article/decision-dna/"),
]

TOPICS = [
    "ライブラリを選ばせる発想は旧来の延長",
    "従来の延長線ではないAI活用",
    "トークンは値より意図を伝える",
    "AIは正解でなくふさわしさを推論する",
    "UIライブラリのヘッドレス化",
]

FORM_LABEL = "✉️ 番組宛の質問フォーム（匿名で投稿できます）"
FORM_URL = "https://forms.gle/bjVAVAn4y78EjL2t6"


def heading(text):
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def paragraph(rich_text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text},
    }


def bullet(rich_text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text},
    }


def text_run(content, url=None):
    run = {"type": "text", "text": {"content": content}}
    if url:
        run["text"]["link"] = {"url": url}
    return run


def main():
    notion = NotionClient()

    blocks = []
    blocks.append(heading("番組概要"))
    blocks.append(paragraph([text_run(DESCRIPTION)]))

    blocks.append(heading("関連リンク"))
    for label, url in LINKS:
        blocks.append(bullet([text_run(label, url)]))

    blocks.append(heading("トピック"))
    for t in TOPICS:
        blocks.append(bullet([text_run(t)]))

    blocks.append(heading("お便り"))
    blocks.append(bullet([text_run(FORM_LABEL, FORM_URL)]))

    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"

    # Fetch first existing block so we can insert "番組概要" section at the very top
    r = requests.get(url, headers=notion.headers)
    r.raise_for_status()
    results = r.json().get("results", [])
    after_id = None  # if None → appends at end
    # We'll append at end (simplest, robust)

    payload = {"children": blocks}
    resp = requests.patch(url, headers=notion.headers, json=payload)
    if resp.status_code >= 300:
        print(f"❌ Failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    print(f"✅ Added {len(blocks)} blocks to page {PAGE_ID}")


if __name__ == "__main__":
    main()
