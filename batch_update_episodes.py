#!/usr/bin/env python3
"""
既存Notionエピソードの一括更新スクリプト

- ページ本文を新テンプレート（Summary / Key Takeaways / Timestamps / Transcript）に書き直す
- 空のCategoryプロパティにLLMで自動分類して設定する

Usage:
    python batch_update_episodes.py                        # ドライラン（変更なし）
    python batch_update_episodes.py --execute --limit 3    # 3件テスト
    python batch_update_episodes.py --execute              # 全件実行
    python batch_update_episodes.py --execute --page-id ID # 1件のみ
    python batch_update_episodes.py --execute --resume     # 中断から再開
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, "src")
sys.path.insert(0, "src/integrations")

import requests
from integrations.notion_client import NotionClient
from utils import load_config

# --- 定数 ---
VALID_CATEGORIES = [
    "Technology", "Biology & Nature", "Science", "Design & Art",
    "Startup & VC", "Education", "Career", "AI", "Others", "Business",
]
PROGRESS_FILE = Path("data/batch_update_progress.json")
BACKUP_DIR = Path("data/batch_backups")


# --- Gemini クライアント（モデルローテーション対応） ---
# 無料枠はモデルごとに独立したクォータを持つため、複数モデルをローテーションして使う
GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

_model_index = 0  # 現在のモデルインデックス


def init_gemini():
    """Geminiクライアントを初期化。利用可能なモデルリストを返す。"""
    try:
        config = load_config()
        api_key = (config.get("gemini") or {}).get("api_key")
        if not api_key:
            return None, []
        from google import genai
        client = genai.Client(api_key=api_key)

        # 利用可能なモデルを確認
        available = []
        for name in GEMINI_MODELS:
            try:
                client.models.generate_content(model=name, contents="ping")
                available.append(name)
                print(f"   ✅ {name} 利用可能")
            except Exception:
                pass
        if available:
            print(f"   📋 {len(available)}モデルでローテーション")
            return client, available
    except Exception:
        pass
    return None, []


def gemini_generate(client, models: list, prompt: str, max_retries: int = 8) -> Optional[str]:
    """Geminiでテキスト生成（モデルローテーション + リトライ）。"""
    global _model_index
    if not client or not models:
        return None

    for attempt in range(max_retries):
        model_name = models[_model_index % len(models)]
        try:
            resp = client.models.generate_content(model=model_name, contents=prompt)
            text = getattr(resp, "text", None)
            return text.strip() if text else None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # 次のモデルに切り替え
                old_model = model_name
                _model_index += 1
                next_model = models[_model_index % len(models)]

                # 全モデルを一巡した場合のみ待機
                if (_model_index % len(models)) == 0:
                    import re as _re
                    match = _re.search(r"retry in (\d+\.?\d*)", err_str, _re.IGNORECASE)
                    wait = int(float(match.group(1))) + 2 if match else 20
                    wait = min(wait, 30)  # 最大30秒
                    print(f"   ⏳ 全モデル制限中: {wait}秒待機 (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                else:
                    print(f"   🔄 {old_model} → {next_model} に切替 (attempt {attempt+1}/{max_retries})")
                    time.sleep(1)
                continue
            if "503" in err_str or "UNAVAILABLE" in err_str:
                # 一時的な過負荷 → 次のモデルへ
                _model_index += 1
                time.sleep(3)
                continue
            print(f"   ⚠️ Gemini error: {e}")
            return None
    print(f"   ⚠️ Gemini: {max_retries}回リトライ後も失敗")
    return None


def regenerate_chapter_titles(client, models: list, title: str, show: str, timestamps: str) -> str:
    """既存 Timestamps ('MM:SS 断片' の羅列) から、適切な章タイトルを再生成する。

    既存エピソードの多くはチャプタータイトルが文字起こしの断片になっている。
    その断片を「内容メモ」として Gemini に渡し、区間の要点を表す短いタイトルに直す。
    失敗時は既存 timestamps をそのまま返す（悪化させない）。
    """
    if not timestamps or not timestamps.strip():
        return timestamps
    ts_lines = [ln.strip() for ln in timestamps.splitlines()
                if re.match(r'^\d{1,2}:\d{2}', ln.strip())]
    if not ts_lines:
        return timestamps
    context = "\n".join(ts_lines)
    prompt = f"""あなたはポッドキャストの編集者です。以下の時刻ごとの内容メモ（文字起こしの断片）から、章タイトル（チャプター目次）を作ってください。

条件:
- 各行の時刻（MM:SS）はそのまま維持（変更しない・行数も同じ）
- 時刻の後に、その区間の要点を表す短いタイトルを付ける（内容と同じ言語で 15〜30文字程度）
- 入力は断片的な文字起こしなので、そのまま使わず要約したタイトルにする
- 出力は「MM:SS タイトル」のみ（余計な説明は禁止）

番組: {show}
回: {title}

内容メモ:
{context}

出力:
""".strip()
    result = gemini_generate(client, models, prompt)
    if not result:
        return timestamps
    out_lines = [ln.strip() for ln in result.splitlines()
                 if re.match(r'^\d{1,2}:\d{2}', ln.strip())]
    return "\n".join(out_lines) if out_lines else timestamps


# --- Notion ヘルパー ---
def fetch_all_pages(notion: NotionClient, limit: Optional[int] = None) -> list:
    """Notion DBから全ページを取得（ページネーション対応）。"""
    url = f"https://api.notion.com/v1/databases/{notion.database_id}/query"
    all_pages = []
    start_cursor = None
    while True:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = requests.post(url, headers=notion.headers, json=payload)
        if resp.status_code != 200:
            print(f"❌ DB取得エラー: {resp.status_code}")
            break
        data = resp.json()
        all_pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
    print(f"📋 全 {len(all_pages)} 件のエピソードを取得")
    if limit:
        all_pages = all_pages[:limit]
        print(f"   → {limit} 件に制限")
    return all_pages


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
        time.sleep(0.2)
    return True


def get_page_title(page: dict) -> str:
    title_list = page.get("properties", {}).get("Name", {}).get("title", [])
    return title_list[0].get("plain_text", "") if title_list else ""


def get_page_category(page: dict) -> Optional[str]:
    cat = page.get("properties", {}).get("Category", {}).get("select")
    return cat.get("name") if cat else None


def get_page_podcast(page: dict) -> str:
    sel = page.get("properties", {}).get("Podcast", {}).get("select")
    return sel.get("name", "") if sel else ""


def extract_block_text(block: dict) -> str:
    """ブロックからプレーンテキストを抽出する。"""
    block_type = block.get("type", "")
    data = block.get(block_type, {})
    rich_text = data.get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich_text)


def extract_sections_from_blocks(blocks: list) -> dict:
    """ブロックリストからセクション別テキストを抽出する。"""
    sections = {"summary": "", "key_takeaways": "", "timestamps": "", "transcript": "", "other": ""}
    current = "other"

    for block in blocks:
        block_type = block.get("type", "")

        if block_type in ("heading_2", "heading_3"):
            text = extract_block_text(block).strip()
            if "Transcript" in text or "文字起こし" in text:
                current = "transcript"
                continue
            elif "Timestamps" in text or "タイムスタンプ" in text:
                current = "timestamps"
                continue
            elif "Summary" in text or "要約" in text:
                current = "summary"
                continue
            elif "Basic Information" in text:
                current = "other"  # スキップ
                continue
            elif "Key Takeaways" in text:
                # 通常フローでは再生成するので無視されるが、chapters-only では再利用する
                current = "key_takeaways"
                continue

        # toggleブロック内のtranscriptも取得
        if block_type == "toggle":
            toggle_text = extract_block_text(block)
            if "Transcript" in toggle_text:
                current = "transcript"
                # toggle childrenがあれば取得
                if block.get("has_children"):
                    # childrenは別途取得が必要だが、ここでは空のまま
                    pass
                continue

        text = extract_block_text(block)
        if text.strip():
            sections[current] += text.strip() + "\n"

    return {k: v.strip() for k, v in sections.items()}


def fetch_toggle_children_text(notion: NotionClient, toggle_block_id: str) -> str:
    """Toggleブロックの子テキストを取得する。"""
    children = fetch_all_block_children(notion, toggle_block_id)
    texts = []
    for child in children:
        text = extract_block_text(child)
        if text.strip():
            texts.append(text.strip())
    return "\n".join(texts)


# --- LLM 生成 ---
def generate_summary_and_takeaways(client, models: list, title: str, show: str, transcript: str) -> tuple:
    """SummaryとKey Takeawaysを生成する。"""
    # 長いtranscriptはチャンク化
    max_chars = 8000
    chunks = []
    if len(transcript) <= max_chars:
        chunks = [transcript]
    else:
        buf = ""
        for part in re.split(r"(\n+|。|！|？)", transcript):
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

    # 長すぎる場合は前半・中間・後半を抽出
    if len(chunks) > 6:
        mid = len(chunks) // 2
        chunks = chunks[:2] + chunks[mid:mid+2] + chunks[-2:]

    # チャンク要約
    chunk_summaries = []
    for idx, chunk in enumerate(chunks, 1):
        prompt = f"""あなたは優秀な編集者です。次のポッドキャスト文字起こし（断片）を日本語で要点整理してください。

条件:
- 断片の要点を箇条書きで5個まで
- 固有名詞/キーワードがあれば含める
- 余計な前置きや自己言及は禁止

番組: {show}
回: {title}

文字起こし（断片 {idx}/{len(chunks)}）:
{chunk}

出力:
- ..."""
        out = gemini_generate(client, models, prompt)
        if out:
            chunk_summaries.append(out)
        time.sleep(0.5)

    # 最終プロンプト
    notes = "\n".join(chunk_summaries) if chunk_summaries else transcript[:12000]
    final_prompt = f"""あなたは優秀な編集者です。以下はポッドキャストの要点メモ（複数断片のまとめ）です。
これを元に、日本語で「Summary」と「Key Takeaways」を作成してください。

【Summaryの条件】
- 250〜450文字程度
- エピソードで実際に議論・紹介された内容を具体的に要約する
- タイトルをそのまま言い換えるだけの要約は禁止
- 番組の定型紹介文（「〜という番組です」など）を含めるのは禁止
- ゲスト紹介だけで終わる要約は禁止
- 「このエピソードでは〜について話されています」という書き方は禁止
- 具体的に何が語られたか、どんな主張・知見・事例・データが紹介されたかを書く

【Key Takeawaysの条件】
- 箇条書きで3〜5点
- このエピソード固有の学び・気づき・主張を書く
- 「〜について学べます」などの抽象的な表現は禁止
- 具体的な数字・事例・人名・概念名を含める

番組: {show}
回: {title}

要点メモ:
{notes}

出力形式（この順番で、見出し行も含めて出力）:
Summary:
...

Key Takeaways:
- ..."""

    final = gemini_generate(client, models, final_prompt)
    if not final:
        return None, None

    parts = re.split(r'Key Takeaways:\s*\n', final, maxsplit=1)
    if len(parts) == 2:
        summary = re.sub(r'^Summary:\s*\n?', '', parts[0]).strip()
        takeaways = parts[1].strip()
        return summary, takeaways
    return final.strip(), None


def classify_category(client, models: list, title: str, show: str, transcript_head: str) -> str:
    """エピソードをカテゴリに分類する。"""
    prompt = f"""Classify this podcast episode into exactly one category.
Return ONLY the category name, nothing else.

Categories: {', '.join(VALID_CATEGORIES)}

Title: {title}
Podcast: {show}
Content: {transcript_head}"""

    result = gemini_generate(client, models, prompt)
    if result:
        category = result.strip().strip('"').strip("'")
        if category in VALID_CATEGORIES:
            return category
        for valid in VALID_CATEGORIES:
            if valid.lower() in category.lower():
                return valid
    return "Others"


def update_category_property(notion: NotionClient, page_id: str, category: str) -> bool:
    """ページのCategoryプロパティを更新する。"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "Category": {
                "select": {"name": category}
            }
        }
    }
    resp = requests.patch(url, headers=notion.headers, json=payload)
    return resp.status_code == 200


# --- 進捗管理 ---
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


# --- メイン処理 ---
def process_page(
    notion: NotionClient,
    gemini_client,
    gemini_models: list,
    page: dict,
    dry_run: bool = True,
    chapters_only: bool = False,
) -> bool:
    """1ページを処理する。"""
    page_id = page["id"]
    title = get_page_title(page)
    show = get_page_podcast(page)
    category = get_page_category(page)
    title_short = (title[:50] + "…") if len(title) > 50 else title

    # ブロック取得
    blocks = fetch_all_block_children(notion, page_id)
    if not blocks:
        print(f"   ⏭️ ブロックなし（スキップ）")
        return False

    # セクション抽出
    sections = extract_sections_from_blocks(blocks)

    # toggleブロック内のtranscriptも取得
    transcript = sections.get("transcript", "")
    if not transcript:
        for block in blocks:
            if block.get("type") == "toggle" and block.get("has_children"):
                toggle_text = extract_block_text(block)
                if "Transcript" in toggle_text:
                    transcript = fetch_toggle_children_text(notion, block["id"])
                    break

    if not transcript or len(transcript) < 50:
        print(f"   ⏭️ Transcriptが見つからないまたは短すぎる（スキップ）")
        return False

    timestamps = sections.get("timestamps", "")

    if dry_run:
        print(f"   📝 Transcript: {len(transcript)}文字, Timestamps: {len(timestamps)}文字")
        print(f"   Category: {category or '(空)'}")
        print(f"   → ドライラン: 変更なし")
        return True

    # バックアップ保存
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_data = {
        "page_id": page_id,
        "title": title,
        "blocks_count": len(blocks),
        "transcript": transcript[:500],
        "timestamps": timestamps[:200],
    }
    backup_path = BACKUP_DIR / f"{page_id.replace('-', '')}.json"
    backup_path.write_text(json.dumps(backup_data, indent=2, ensure_ascii=False))

    if chapters_only:
        # 既存の Summary / Key Takeaways / Category を保持し、チャプターだけ直す
        summary = sections.get("summary", "")
        takeaways = sections.get("key_takeaways", "")
        new_category = None
        if not summary:
            print(f"   ⏭️ 既存 Summary が空（chapters-only スキップ）")
            return False
        if not timestamps:
            print(f"   ⏭️ Timestamps が空（chapters-only スキップ）")
            return False
    else:
        # LLMでSummary + Key Takeaways生成
        print(f"   🧠 Summary + Key Takeaways生成中...")
        summary, takeaways = generate_summary_and_takeaways(
            gemini_client, gemini_models, title, show, transcript
        )
        if not summary:
            print(f"   ❌ Summary生成失敗（スキップ）")
            return False

        # Category分類（空の場合のみ）
        new_category = None
        if not category:
            print(f"   🏷️ Category分類中...")
            new_category = classify_category(
                gemini_client, gemini_models, title, show, transcript[:300]
            )
            print(f"   → Category: {new_category}")

    # 新テンプレートでMarkdown生成
    takeaways_section = ""
    if takeaways:
        takeaways_section = f"""## Key Takeaways

{takeaways}

"""

    timestamps_section = ""
    if timestamps:
        print(f"   📑 チャプタータイトル再生成中...")
        timestamps = regenerate_chapter_titles(
            gemini_client, gemini_models, title, show, timestamps
        )
        timestamps_section = f"""## Timestamps

{timestamps}

"""

    # Transcriptを文末で改行整形
    formatted_transcript = transcript
    formatted_transcript = re.sub(r'([。！？.!?])', r'\1\n\n', formatted_transcript).strip()
    parts = [p.strip() for p in formatted_transcript.split("\n\n") if p.strip()]
    formatted_transcript = "\n\n".join(parts)

    new_markdown = f"""## Summary

{summary}

{takeaways_section}{timestamps_section}## Transcript

{formatted_transcript}
"""

    # 既存ブロック削除
    child_ids = [b["id"] for b in blocks]
    print(f"   🗑️ {len(child_ids)} ブロック削除中...")
    if not delete_all_blocks(notion, child_ids):
        print(f"   ❌ ブロック削除失敗")
        return False

    # 新ブロック追加
    new_blocks = notion._markdown_to_notion_blocks(new_markdown)
    transcript_overflow = notion._transcript_overflow_blocks
    print(f"   📤 {len(new_blocks)} ブロック追加中...")
    if not notion._append_blocks_to_page(page_id, new_blocks):
        print(f"   ❌ ブロック追加失敗")
        return False

    # toggle overflowの処理
    if transcript_overflow:
        toggle_id = notion._find_toggle_block_id(page_id)
        if toggle_id:
            print(f"   📤 Toggle に残り {len(transcript_overflow)} ブロック追加中...")
            notion._append_blocks_to_page(toggle_id, transcript_overflow)

    # Categoryプロパティ更新
    if new_category:
        if update_category_property(notion, page_id, new_category):
            print(f"   🏷️ Category → {new_category}")
        else:
            print(f"   ⚠️ Category更新失敗")

    return True


def main():
    parser = argparse.ArgumentParser(description="既存Notionエピソードの一括更新")
    parser.add_argument("--execute", action="store_true", help="実際に更新を実行（省略時はドライラン）")
    parser.add_argument("--limit", type=int, help="処理件数の上限")
    parser.add_argument("--page-id", type=str, help="特定ページのみ処理")
    parser.add_argument("--resume", action="store_true", help="前回の中断から再開")
    parser.add_argument("--chapters-only", action="store_true",
                        help="Summary/Takeaways は保持し、チャプタータイトルのみ再生成する")
    args = parser.parse_args()

    notion = NotionClient()
    gemini_client, gemini_models = init_gemini()

    if not gemini_client or not gemini_models:
        print("❌ Geminiクライアントの初期化に失敗しました")
        return

    dry_run = not args.execute
    if dry_run:
        print("🔍 ドライランモード（--execute で実行）\n")
    else:
        print("🚀 実行モード\n")

    # ページ取得
    if args.page_id:
        page_id = args.page_id.strip().replace("-", "")
        if len(page_id) == 32:
            page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:32]}"
        resp = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=notion.headers,
        )
        if resp.status_code != 200:
            print(f"❌ ページ取得エラー: {resp.status_code}")
            return
        pages = [resp.json()]
    else:
        pages = fetch_all_pages(notion, limit=args.limit)

    if not pages:
        print("❌ ページが0件です")
        return

    # 進捗管理
    progress = load_progress() if args.resume else {}

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, page in enumerate(pages, 1):
        page_id = page["id"]
        title = get_page_title(page)
        title_short = (title[:50] + "…") if len(title) > 50 else title

        # 処理済みスキップ
        if args.resume and progress.get(page_id) == "done":
            print(f"[{i}/{len(pages)}] {title_short} → 処理済み（スキップ）")
            skip_count += 1
            continue

        print(f"\n[{i}/{len(pages)}] {title_short}")

        try:
            result = process_page(notion, gemini_client, gemini_models, page,
                                  dry_run=dry_run, chapters_only=args.chapters_only)
            if result:
                success_count += 1
                if not dry_run:
                    progress[page_id] = "done"
                    save_progress(progress)
            else:
                skip_count += 1
        except Exception as e:
            print(f"   ❌ エラー: {e}")
            error_count += 1
            if not dry_run:
                progress[page_id] = f"error: {str(e)[:100]}"
                save_progress(progress)

        # レート制限対策
        if not dry_run:
            time.sleep(1.0)

    print(f"\n{'='*60}")
    print(f"✅ 完了: 成功 {success_count} / スキップ {skip_count} / エラー {error_count}")
    if dry_run:
        print("   ※ ドライランのため変更はありません。--execute で実行してください。")


if __name__ == "__main__":
    main()
