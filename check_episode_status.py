#!/usr/bin/env python3
"""
Notionエピソードのカバー画像とSpotify URLの状態を確認するスクリプト
"""

import requests
from config.settings import NOTION_API_KEY, NOTION_DATABASE_ID

DATABASE_ID_RAW = NOTION_DATABASE_ID.replace("-", "")
DATABASE_ID = (
    f"{DATABASE_ID_RAW[:8]}-{DATABASE_ID_RAW[8:12]}-{DATABASE_ID_RAW[12:16]}-{DATABASE_ID_RAW[16:20]}-{DATABASE_ID_RAW[20:32]}"
    if len(DATABASE_ID_RAW) == 32
    else NOTION_DATABASE_ID
)

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def get_all_pages():
    """全ページを取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_pages = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            break

        data = response.json()
        all_pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_pages


def extract_spotify_url(page):
    """ページからSpotify URLを抽出"""
    props = page.get("properties", {})
    url_prop = props.get("URL", {})
    if url_prop.get("type") == "url":
        url = url_prop.get("url")
        if url and "spotify.com/episode" in url:
            return url
    return None


def get_title(page):
    """ページタイトルを取得"""
    props = page.get("properties", {})
    title_prop = props.get("Name", {})
    if title_prop.get("type") == "title":
        title_parts = title_prop.get("title", [])
        if title_parts:
            return title_parts[0].get("plain_text", "")
    return "Unknown"


def main():
    pages = get_all_pages()
    print(f"📊 総エピソード数: {len(pages)}\n")

    stats = {
        "with_cover_with_url": [],
        "with_cover_no_url": [],
        "no_cover_with_url": [],
        "no_cover_no_url": [],
    }

    for page in pages:
        title = get_title(page)
        cover = page.get("cover")
        spotify_url = extract_spotify_url(page)

        has_cover = cover is not None
        has_url = spotify_url is not None

        if has_cover and has_url:
            stats["with_cover_with_url"].append((title, spotify_url))
        elif has_cover and not has_url:
            stats["with_cover_no_url"].append(title)
        elif not has_cover and has_url:
            stats["no_cover_with_url"].append((title, spotify_url))
        else:
            stats["no_cover_no_url"].append(title)

    print("=" * 60)
    print("📈 統計結果")
    print("=" * 60)
    print(f"✅ カバー画像あり + Spotify URLあり: {len(stats['with_cover_with_url'])}件")
    print(f"✅ カバー画像あり + Spotify URLなし: {len(stats['with_cover_no_url'])}件")
    print(f"❌ カバー画像なし + Spotify URLあり: {len(stats['no_cover_with_url'])}件")
    print(f"⏭️  カバー画像なし + Spotify URLなし: {len(stats['no_cover_no_url'])}件")
    print("=" * 60)

    if stats["no_cover_with_url"]:
        print(
            f"\n⚠️  処理が必要なエピソード（カバー画像なし + URLあり）: {len(stats['no_cover_with_url'])}件\n"
        )
        for i, (title, url) in enumerate(stats["no_cover_with_url"][:10], 1):
            print(f"{i}. {title[:60]}")
            print(f"   URL: {url[:60]}...")
        if len(stats["no_cover_with_url"]) > 10:
            print(f"\n... 他 {len(stats['no_cover_with_url']) - 10}件")

    if stats["no_cover_no_url"]:
        print(
            f"\n⏭️  Spotify URLが設定されていないエピソード: {len(stats['no_cover_no_url'])}件\n"
        )
        for i, title in enumerate(stats["no_cover_no_url"][:10], 1):
            print(f"{i}. {title[:60]}")
        if len(stats["no_cover_no_url"]) > 10:
            print(f"\n... 他 {len(stats['no_cover_no_url']) - 10}件")


if __name__ == "__main__":
    main()
