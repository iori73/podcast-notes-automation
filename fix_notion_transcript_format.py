#!/usr/bin/env python3
"""
直近10件のNotionページを取得し、トランスクリプトを文末（。！？）で改行して読みやすくする。
ローカルの episode_summary.md がある場合はその内容で置き換え、ない場合はNotionから取得した
Transcript部分のみを改行付きで差し替える。
"""

import re
import time
import requests
from pathlib import Path
from typing import Optional

sys_path_ok = False
for p in ["src", "src/integrations"]:
    if p not in __import__("sys").path:
        __import__("sys").path.insert(0, p)
        sys_path_ok = True

from integrations.notion_client import NotionClient


def reformat_transcript_in_markdown(md: str) -> str:
    """Markdown内の ## **Transcript** セクションを、文末（。！？ . ! ?）で改行するよう整形する。"""
    # Transcript セクション: "## **Transcript**" の直後から次の "## " または末尾まで
    pattern = r"(## \*\*Transcript\*\*\s*\n\n)(.*?)(?=\n## |\Z)"
    flags = re.DOTALL

    def _break_long_line(text: str, max_len: int = 120) -> str:
        """長い1行を max_len 付近でスペース/読点の直後に改行する。"""
        if len(text) <= max_len:
            return text
        lines = []
        rest = text
        while rest:
            rest = rest.lstrip()
            if not rest:
                break
            if len(rest) <= max_len:
                lines.append(rest)
                break
            chunk = rest[: max_len + 1]
            break_at = -1
            for sep in (" ", "、", "。", ".", "」", "）"):
                pos = chunk.rfind(sep)
                if pos > max_len // 2:
                    break_at = pos + 1
                    break
            if break_at <= 0:
                break_at = max_len
            lines.append(rest[:break_at].strip())
            rest = rest[break_at:]
        return "\n\n".join(lines)

    def replace_section(match):
        header, body = match.group(1), match.group(2)
        if not body.strip():
            return match.group(0)
        # 文末の直後に改行を挿入（日本語。！？＋英語. ! ?）
        formatted = re.sub(r"([。！？.!?])", r"\1\n\n", body.strip()).strip()
        # 句点が少なく長い塊が残る場合は、約120文字ごとに改行
        lines = []
        for part in formatted.split("\n\n"):
            part = part.strip()
            if part:
                lines.append(_break_long_line(part, 120))
        formatted = "\n\n".join(lines) if lines else formatted
        return header + formatted

    return re.sub(pattern, replace_section, md, flags=flags)


def get_page_title(page: dict) -> str:
    """Notionページオブジェクトからタイトルを取得。"""
    title_list = page.get("properties", {}).get("Name", {}).get("title", [])
    if not title_list:
        return ""
    return title_list[0].get("plain_text", "")


def safe_title_for_path(title: str) -> str:
    """ファイルパス用に安全なタイトルに変換。"""
    return title.replace("/", "／").replace(":", "：").replace("?", "？").strip()


def find_local_markdown(notion_title: str) -> Optional[Path]:
    """Notionのタイトルに対応する data/outputs/<safe_title>/episode_summary.md を探す。"""
    outputs_dir = Path("data/outputs")
    if not outputs_dir.exists():
        return None
    safe = safe_title_for_path(notion_title)
    path = outputs_dir / safe / "episode_summary.md"
    if path.exists():
        return path
    # 部分一致で探す（タイトルがNotionで短縮されている場合など）
    for d in outputs_dir.iterdir():
        if not d.is_dir():
            continue
        if notion_title in d.name or d.name in notion_title or safe in d.name:
            p = d / "episode_summary.md"
            if p.exists():
                return p
    return None


def fetch_all_block_children(notion: NotionClient, block_id: str) -> list:
    """ページの子ブロックを全て取得（ページネーション対応）。"""
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    all_blocks = []
    params = {"page_size": 100}
    while True:
        resp = requests.get(url, headers=notion.headers, params=params)
        if resp.status_code != 200:
            break
        data = resp.json()
        all_blocks.extend(data.get("results", []))
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break
        params = {"page_size": 100, "start_cursor": next_cursor}
    return all_blocks


def delete_all_blocks(notion: NotionClient, block_ids: list) -> bool:
    """指定したブロックIDをすべて削除する。"""
    for bid in block_ids:
        for attempt in range(3):
            r = requests.delete(f"https://api.notion.com/v1/blocks/{bid}", headers=notion.headers)
            if r.status_code in (200, 204):
                break
            if r.status_code == 502 and attempt < 2:
                time.sleep(2.0)
                continue
            print(f"   ⚠️ ブロック削除失敗: {bid} -> {r.status_code}")
            return False
        time.sleep(0.2)  # Notion API レート制限対策
    return True


def main():
    import sys
    notion = NotionClient()
    db_id = notion.database_id

    # 単一ページを URL または page_id で指定した場合
    page_id_arg = None
    if "--page-id" in sys.argv:
        try:
            i = sys.argv.index("--page-id") + 1
            if i < len(sys.argv):
                page_id_arg = sys.argv[i].strip().replace("-", "")
                if len(page_id_arg) == 32:
                    page_id_arg = f"{page_id_arg[:8]}-{page_id_arg[8:12]}-{page_id_arg[12:16]}-{page_id_arg[16:20]}-{page_id_arg[20:32]}"
        except (ValueError, IndexError):
            pass

    if page_id_arg:
        # 1ページだけ取得（指定IDのページ情報を取得）
        page_url = f"https://api.notion.com/v1/pages/{page_id_arg}"
        resp = requests.get(page_url, headers=notion.headers)
        if resp.status_code != 200:
            print(f"❌ ページ取得エラー: {resp.status_code}")
            return
        pages = [resp.json()]
    else:
        # 直近10件のページを取得（作成日時降順）
        query_url = "https://api.notion.com/v1/databases/" + db_id + "/query"
        payload = {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 10,
        }
        resp = requests.post(query_url, headers=notion.headers, json=payload)
        if resp.status_code != 200:
            print(f"❌ データベース取得エラー: {resp.status_code}")
            print(resp.text[:500])
            return
        # 処理件数（--limit N で指定可能。未指定なら10件）
        limit_pages = 10
        if "--limit" in sys.argv:
            try:
                i = sys.argv.index("--limit") + 1
                if i < len(sys.argv):
                    limit_pages = int(sys.argv[i])
            except (ValueError, IndexError):
                pass
        pages = resp.json().get("results", [])[:limit_pages]
    if not pages:
        print("❌ ページが0件です")
        return

    db_url = f"https://www.notion.so/{notion.database_id.replace('-', '')}"
    print(f"📋 対象DB: {db_url}")
    print(f"📋 直近 {len(pages)} 件のNotionページを処理します（1ページあたりブロック削除・追加のため時間がかかります）\n")

    for i, page in enumerate(pages, 1):
        page_id = page["id"]
        title = get_page_title(page)
        title_short = (title[:50] + "…") if len(title) > 50 else title
        print(f"[{i}/{len(pages)}] {title_short}")

        md_path = find_local_markdown(title)
        if not md_path:
            print(f"   ⏭️ ローカルに episode_summary.md がないためスキップ")
            continue

        with open(md_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        markdown_fixed = reformat_transcript_in_markdown(markdown_content)
        if markdown_fixed == markdown_content:
            print("   ⏭️ Transcript の変更なし（スキップ）")
            continue

        # 既存の子ブロックを取得
        children = fetch_all_block_children(notion, page_id)
        if children:
            child_ids = [b["id"] for b in children]
            print(f"   削除: {len(child_ids)} ブロック...", flush=True)
            if not delete_all_blocks(notion, child_ids):
                print("   ❌ ブロック削除に失敗")
                continue
        else:
            print("   既存ブロックなし（新規追加のみ）", flush=True)

        # 改行付きマークダウンでブロックを生成して追加
        new_blocks = notion._markdown_to_notion_blocks(markdown_fixed)
        print(f"   追加: {len(new_blocks)} ブロック...", flush=True)
        if not notion._append_blocks_to_page(page_id, new_blocks):
            print("   ❌ ブロック追加に失敗")
            continue

        page_url = page.get("url", "") or f"https://www.notion.so/{page_id.replace('-', '')}"
        print(f"   ✅ 更新完了: {page_url}")

    print("\n✅ 処理完了")


if __name__ == "__main__":
    main()
