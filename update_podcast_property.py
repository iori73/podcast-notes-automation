#!/usr/bin/env python3
"""
Notionエピソードの"Podcast"プロパティが空白の場合、
Spotify URLやタイトルからポッドキャスト名を取得して更新するスクリプト
"""

import requests
import time
from typing import Dict, List, Optional
from config.settings import NOTION_API_KEY, NOTION_DATABASE_ID

# Spotify APIクライアント
try:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from spotify import SpotifyClient
    SPOTIFY_API_AVAILABLE = True
except ImportError:
    SPOTIFY_API_AVAILABLE = False
    print("⚠️  Spotify APIクライアントが利用できません")

# Listen Notes APIクライアント
try:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from listen_notes import ListenNotesClient
    LISTEN_NOTES_API_AVAILABLE = True
except ImportError:
    LISTEN_NOTES_API_AVAILABLE = False
    print("⚠️  Listen Notes APIクライアントが利用できません")

# Notion API設定
NOTION_TOKEN = NOTION_API_KEY
DATABASE_ID_RAW = NOTION_DATABASE_ID.replace("-", "")
DATABASE_ID = (
    f"{DATABASE_ID_RAW[:8]}-{DATABASE_ID_RAW[8:12]}-{DATABASE_ID_RAW[12:16]}-{DATABASE_ID_RAW[16:20]}-{DATABASE_ID_RAW[20:32]}"
    if len(DATABASE_ID_RAW) == 32
    else NOTION_DATABASE_ID
)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def get_database_pages() -> List[Dict]:
    """Notionデータベースから全ページを取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_pages = []
    has_more = True
    start_cursor = None
    batch_count = 0

    while has_more:
        batch_count += 1
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code != 200:
            print(f"Error fetching pages: {response.status_code}")
            print(response.text)
            break

        data = response.json()
        pages_in_batch = data.get("results", [])
        all_pages.extend(pages_in_batch)
        print(f"📋 バッチ {batch_count}: {len(pages_in_batch)}件取得 (累計: {len(all_pages)}件)")

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    print(f"✅ 全{len(all_pages)}件のエピソードを取得しました\n")
    return all_pages


def get_page_title(page: Dict) -> str:
    """Notionページのタイトルを取得"""
    properties = page.get("properties", {})
    for prop_name in ["Title", "title", "名前", "Name"]:
        if prop_name in properties:
            prop = properties[prop_name]
            if prop.get("type") == "title":
                title_array = prop.get("title", [])
                if title_array:
                    return title_array[0].get("plain_text", "Unknown")
    return "Unknown"


def extract_spotify_url_from_page(page: Dict) -> Optional[str]:
    """NotionページからSpotify URLを抽出"""
    properties = page.get("properties", {})
    url_property_names = ["URL", "url", "Spotify URL", "Spotify", "Link", "リンク"]

    for prop_name in url_property_names:
        if prop_name in properties:
            prop = properties[prop_name]
            prop_type = prop.get("type")

            if prop_type == "url":
                url = prop.get("url")
                if url and "spotify.com/episode" in url:
                    return url
            elif prop_type == "rich_text":
                rich_text = prop.get("rich_text", [])
                if rich_text:
                    url = rich_text[0].get("plain_text", "")
                    if "spotify.com/episode" in url:
                        return url

    return None


def get_podcast_name_from_spotify(spotify_url: str) -> Optional[str]:
    """Spotify URLからポッドキャスト名を取得"""
    if not SPOTIFY_API_AVAILABLE:
        return None

    try:
        spotify_client = SpotifyClient()
        episode_id = spotify_url.split("/")[-1].split("?")[0]
        episode = spotify_client.sp.episode(episode_id, market="JP")
        
        show_name = episode.get("show", {}).get("name", "")
        if show_name:
            return show_name
    except Exception as e:
        print(f"  ⚠️  Spotify APIエラー: {e}")
    
    return None


def get_podcast_name_from_listen_notes(episode_title: str) -> Optional[str]:
    """Listen Notes APIでエピソードを検索してポッドキャスト名を取得"""
    if not LISTEN_NOTES_API_AVAILABLE:
        return None

    try:
        ln_client = ListenNotesClient()
        ln_client.set_language("Japanese")
        
        episode = ln_client.search_episode(episode_title)
        if episode:
            podcast_name = episode.get("podcast_title_original")
            if podcast_name:
                return podcast_name
    except Exception as e:
        print(f"  ⚠️  Listen Notes APIエラー: {e}")
    
    return None


def get_podcast_options() -> Dict[str, str]:
    """NotionデータベースのPodcastプロパティの選択肢を取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        return {}
    
    db = response.json()
    props = db.get("properties", {})
    
    if "Podcast" not in props:
        return {}
    
    podcast_prop = props["Podcast"]
    if podcast_prop.get("type") != "select":
        return {}
    
    options = podcast_prop.get("select", {}).get("options", [])
    # 選択肢の名前をキーとして、そのIDを値として返す（実際は名前だけで更新可能）
    return {opt.get("name", ""): opt.get("name", "") for opt in options}


def update_notion_podcast_property(page_id: str, podcast_name: str) -> bool:
    """NotionページのPodcastプロパティを更新"""
    try:
        # まずページのプロパティ構造を取得
        page_url = f"https://api.notion.com/v1/pages/{page_id}"
        page_response = requests.get(page_url, headers=HEADERS)
        
        if page_response.status_code != 200:
            return False
        
        page_data = page_response.json()
        properties = page_data.get("properties", {})
        
        # Podcastプロパティ名を探す
        podcast_property_name = None
        for prop_name in ["Podcast", "podcast", "番組", "Show"]:
            if prop_name in properties:
                prop = properties[prop_name]
                if prop.get("type") == "select":
                    podcast_property_name = prop_name
                    break
        
        if not podcast_property_name:
            print(f"  ⚠️  Podcastプロパティが見つかりません")
            return False
        
        # 選択肢を確認して、既存の選択肢に含まれているかチェック
        podcast_options = get_podcast_options()
        
        # 完全一致を探す
        exact_match = None
        for option_name in podcast_options.keys():
            if option_name.lower() == podcast_name.lower():
                exact_match = option_name
                break
        
        # 部分一致を探す（完全一致がない場合）
        if not exact_match:
            for option_name in podcast_options.keys():
                if podcast_name.lower() in option_name.lower() or option_name.lower() in podcast_name.lower():
                    exact_match = option_name
                    print(f"  ℹ️  部分一致で選択: {option_name}")
                    break
        
        # 使用するポッドキャスト名
        selected_name = exact_match if exact_match else podcast_name
        
        # Podcastプロパティを更新
        payload = {
            "properties": {
                podcast_property_name: {
                    "select": {"name": selected_name}
                }
            }
        }
        
        response = requests.patch(page_url, headers=HEADERS, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            print(f"  ❌ Podcastプロパティの更新に失敗: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return False


def main():
    """メイン処理"""
    print("🎙️  NotionエピソードのPodcastプロパティを更新します...\n")
    print(f"📌 データベースID: {DATABASE_ID}\n")

    pages = get_database_pages()
    print(f"✅ {len(pages)}件のエピソードが見つかりました\n")

    updated_count = 0
    skipped_count = 0
    failed_count = 0
    no_url_count = 0

    for i, page in enumerate(pages, 1):
        page_id = page.get("id", "")
        title = get_page_title(page)
        spotify_url = extract_spotify_url_from_page(page)

        print(f"[{i}/{len(pages)}] {title[:60]}...")

        # Podcastプロパティが空白かどうかを確認
        props = page.get("properties", {})
        podcast_prop = None
        podcast_prop_name = None
        for prop_name in ["Podcast", "podcast", "番組", "Show"]:
            if prop_name in props:
                podcast_prop = props[prop_name]
                podcast_prop_name = prop_name
                break

        if not podcast_prop:
            print(f"  ⚠️  Podcastプロパティが見つかりません（スキップ）")
            skipped_count += 1
            continue

        # Podcastプロパティが空白かどうかを確認
        is_empty = False
        prop_type = podcast_prop.get("type")
        if prop_type == "select":
            select_value = podcast_prop.get("select")
            is_empty = select_value is None
        elif prop_type == "rich_text":
            rich_text = podcast_prop.get("rich_text", [])
            is_empty = len(rich_text) == 0 or not rich_text[0].get("plain_text", "").strip()

        if not is_empty:
            print(f"  ℹ️  既にPodcastプロパティが設定されています（スキップ）")
            skipped_count += 1
            continue

        # Spotify URLからポッドキャスト名を取得
        podcast_name = None
        if spotify_url:
            print(f"  🔗 Spotify URL: {spotify_url}")
            print(f"  🔍 Spotify APIからポッドキャスト名を取得中...")
            podcast_name = get_podcast_name_from_spotify(spotify_url)
            if podcast_name:
                print(f"  ✅ ポッドキャスト名を取得: {podcast_name}")
        else:
            print(f"  ⚠️  Spotify URLが見つかりませんでした")
            no_url_count += 1

        # Spotify APIで取得できなかった場合、Listen Notes APIを試す
        if not podcast_name and LISTEN_NOTES_API_AVAILABLE:
            print(f"  🔄 Listen Notes APIでエピソードを検索中...")
            podcast_name = get_podcast_name_from_listen_notes(title)
            if podcast_name:
                print(f"  ✅ Listen Notesからポッドキャスト名を取得: {podcast_name}")

        # ポッドキャスト名が取得できなかった場合
        if not podcast_name:
            print(f"  ⚠️  ポッドキャスト名の取得に失敗（スキップ）")
            failed_count += 1
            continue

        # NotionページのPodcastプロパティを更新
        print(f"  📝 Podcastプロパティを更新中...")
        if update_notion_podcast_property(page_id, podcast_name):
            print(f"  ✅ Podcastプロパティを更新しました: {podcast_name}")
            updated_count += 1
        else:
            print(f"  ❌ Podcastプロパティの更新に失敗")
            failed_count += 1

        # レート制限対策
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("📊 処理結果")
    print("=" * 60)
    print(f"✅ Podcastプロパティ更新成功: {updated_count}件")
    print(f"⏭️  スキップ（既に設定済み）: {skipped_count}件")
    print(f"⚠️  Spotify URLなし: {no_url_count}件")
    print(f"❌ 失敗: {failed_count}件")
    print(f"📋 合計: {len(pages)}件")
    print("=" * 60)


if __name__ == "__main__":
    main()

