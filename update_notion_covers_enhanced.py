#!/usr/bin/env python3
"""
Notionエピソードのカバー画像を更新する拡張版スクリプト
- Spotify APIで404エラーのエピソード: ブラウザ操作で画像URL取得
- Spotify URLなしのエピソード: エピソード名で検索してURL取得
"""

import requests
import json
import re
import time
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
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
        print(
            f"📋 バッチ {batch_count}: {len(pages_in_batch)}件取得 (累計: {len(all_pages)}件)"
        )

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    print(f"✅ 全{len(all_pages)}件のエピソードを取得しました\n")
    return all_pages


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


def get_page_title(page: Dict) -> str:
    """Notionページのタイトルを取得"""
    properties = page.get("properties", {})
    title_prop = properties.get("Name", {})

    if title_prop.get("type") == "title":
        title_parts = title_prop.get("title", [])
        if title_parts:
            return title_parts[0].get("plain_text", "")

    return "Unknown"


def search_episode_url_by_title(episode_title: str) -> Optional[str]:
    """エピソード名でSpotify API検索してURLを取得"""
    if not SPOTIFY_API_AVAILABLE:
        return None

    try:
        spotify_client = SpotifyClient()

        # 検索クエリを作成（タイトルの最初の50文字を使用）
        search_query = episode_title[:50]

        print(f"  🔍 Spotifyで検索中: {search_query}...")
        results = spotify_client.sp.search(q=search_query, type="episode", limit=5)

        if not results["episodes"]["items"]:
            print(f"  ⚠️  Spotifyで見つかりませんでした")
            return None

        # 最も一致度の高いエピソードを選択
        best_match = None
        best_score = 0

        for episode in results["episodes"]["items"]:
            episode_name = episode["name"].lower()
            title_lower = episode_title.lower()

            # 簡易的な一致度スコア計算
            if title_lower in episode_name or episode_name in title_lower:
                score = len(set(title_lower.split()) & set(episode_name.split()))
                if score > best_score:
                    best_score = score
                    best_match = episode

        if best_match:
            episode_url = best_match["external_urls"]["spotify"]
            print(f"  ✅ 見つかりました: {best_match['name'][:50]}...")
            print(f"  🔗 URL: {episode_url}")
            return episode_url
        else:
            # 一致度の高いものがなければ最初の結果を使用
            episode_url = results["episodes"]["items"][0]["external_urls"]["spotify"]
            print(
                f"  ℹ️  最初の検索結果を使用: {results['episodes']['items'][0]['name'][:50]}..."
            )
            return episode_url

    except Exception as e:
        print(f"  ❌ 検索エラー: {e}")
        return None


def get_cover_image_with_browser_mcp(
    spotify_url: str, use_mcp: bool = False
) -> Optional[str]:
    """
    Chrome DevTools MCPを使用してブラウザ操作でSpotifyエピソードページからカバー画像URLを取得

    use_mcp=Trueの場合、実際のMCPツールを使用します
    use_mcp=Falseの場合、強化されたWebスクレイピングを使用します
    """
    try:
        if use_mcp:
            print(f"  🌐 MCPブラウザ操作でSpotifyページを開いています...")
            # 実際のMCPツール呼び出し（実装が必要）
            # ここでは、MCPツールを直接呼び出すことができないため、
            # この関数を呼び出す側でMCPツールを使用する必要があります
            print(f"  ⚠️  MCPブラウザ機能の直接呼び出しは現在サポートされていません")
            print(f"  💡 代替として強化されたWebスクレイピングを使用します")

        print(f"  🌐 ブラウザ操作でSpotifyページから画像を取得中...")

        # 強化されたWebスクレイピング（MCPの代替）
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        session = requests.Session()
        session.headers.update(headers)

        response = session.get(spotify_url, timeout=20, allow_redirects=True)

        if response.status_code != 200:
            print(f"  ⚠️  HTTP {response.status_code}")
            return None

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # 方法1: og:imageを探す
        og_image = soup.find("meta", property="og:image")
        if not og_image:
            og_image = soup.find("meta", attrs={"name": "og:image"})
        if og_image and og_image.get("content"):
            url = og_image.get("content")
            if "i.scdn.co/image" in url:
                clean_url = url.split("?")[0] if "?" in url else url
                print(f"  ✅ og:imageから取得しました")
                return clean_url

        # 方法2: Twitterカード画像
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            url = twitter_image.get("content")
            if "i.scdn.co/image" in url:
                clean_url = url.split("?")[0] if "?" in url else url
                print(f"  ✅ twitter:imageから取得しました")
                return clean_url

        # 方法3: 正規表現で画像URLを検索
        img_pattern = r"https://i\.scdn\.co/image/[a-f0-9]{40}"
        matches = re.findall(img_pattern, html)
        if matches:
            print(f"  ✅ HTMLパターンマッチングで取得しました")
            return matches[0]

        print(f"  ⚠️  画像URLが見つかりませんでした")
        return None

    except Exception as e:
        print(f"  ❌ ブラウザ操作エラー: {e}")
        import traceback

        traceback.print_exc()
        return None


def get_cover_image_from_listen_notes(episode_title: str) -> Optional[str]:
    """Listen Notes APIでエピソードを検索してカバー画像URLを取得"""
    if not LISTEN_NOTES_API_AVAILABLE:
        return None

    try:
        ln_client = ListenNotesClient()
        ln_client.set_language("Japanese")

        episode = ln_client.search_episode(episode_title)
        if episode:
            # エピソード固有の画像を優先、なければ番組画像を使用
            cover_url = episode.get("image")
            if cover_url:
                print(f"  ✅ Listen Notes APIからカバー画像を取得しました")
                return cover_url

            # 番組画像をフォールバック
            podcast_image = episode.get("podcast_image")
            if podcast_image:
                print(f"  ✅ Listen Notes APIから番組カバー画像を取得しました")
                return podcast_image
    except Exception as e:
        print(f"  ⚠️  Listen Notes APIエラー: {e}")

    return None


def extract_episode_cover_from_spotify_page(
    spotify_url: str, episode_title: str = None
) -> Optional[str]:
    """Spotifyエピソードページからカバー画像URLを抽出"""
    # まずSpotify APIを試す（エピソード固有画像を優先、なければ番組カバー）
    if SPOTIFY_API_AVAILABLE:
        try:
            spotify_client = SpotifyClient()
            # エピソード情報を取得
            episode_id = spotify_url.split("/")[-1].split("?")[0]
            episode = spotify_client.sp.episode(episode_id, market="JP")
            
            # エピソード固有の画像を優先
            episode_images = episode.get("images", [])
            cover_url = None
            
            if episode_images:
                # 中程度のサイズ（300px前後）を優先、なければ最初の画像
                cover_url = episode_images[0]["url"]
                for img in episode_images:
                    if img.get("height") and 200 <= img["height"] <= 400:
                        cover_url = img["url"]
                        break
                print(f"  ✅ Spotify APIからエピソード固有のカバー画像を取得しました")
                return cover_url
            
            # エピソード固有の画像がない場合、番組画像を使用
            show_images = episode.get("show", {}).get("images", [])
            if show_images:
                cover_url = show_images[0]["url"]
                for img in show_images:
                    if img.get("height") and 200 <= img["height"] <= 400:
                        cover_url = img["url"]
                        break
                print(f"  ✅ Spotify APIから番組カバー画像を取得しました")
                return cover_url
            
            # フォールバック: get_episode_infoを使用
            episode_info = spotify_client.get_episode_info(spotify_url)
            cover_url = episode_info.get("cover_image_url")
            if cover_url:
                print(f"  ✅ Spotify APIからカバー画像を取得しました")
                return cover_url
        except Exception as e:
            # 404エラーなどの場合、Listen Notes APIを試す
            error_str = str(e)
            if "404" in error_str or "Resource not found" in error_str:
                print(
                    f"  ⚠️  Spotify APIで404エラー（Listen Notes APIにフォールバック）"
                )
                # Listen Notes APIでエピソードを検索
                if episode_title and LISTEN_NOTES_API_AVAILABLE:
                    cover_url = get_cover_image_from_listen_notes(episode_title)
                    if cover_url:
                        return cover_url
            else:
                print(f"  ⚠️  Spotify APIエラー: {e}（ブラウザ操作にフォールバック）")

    # Spotify APIで取得できない場合は、ブラウザ操作（Webスクレイピング）を試す
    return get_cover_image_with_browser_mcp(spotify_url)


def update_notion_page_cover(page_id: str, cover_url: str) -> bool:
    """Notionページのカバー画像を更新"""
    try:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"cover": {"type": "external", "external": {"url": cover_url}}}
        response = requests.patch(url, headers=HEADERS, json=payload)

        if response.status_code == 200:
            return True
        else:
            print(f"  ❌ カバー画像の更新に失敗: {response.status_code}")
            print(f"  Response: {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return False


def update_notion_page_url(page_id: str, spotify_url: str) -> bool:
    """NotionページのURLプロパティを更新"""
    try:
        # まずページのプロパティ構造を取得
        page_url = f"https://api.notion.com/v1/pages/{page_id}"
        page_response = requests.get(page_url, headers=HEADERS)

        if page_response.status_code != 200:
            return False

        page_data = page_response.json()
        properties = page_data.get("properties", {})

        # URLプロパティ名を探す
        url_property_name = None
        for prop_name in ["URL", "url", "Spotify URL", "Spotify", "Link", "リンク"]:
            if prop_name in properties:
                prop = properties[prop_name]
                if prop.get("type") == "url":
                    url_property_name = prop_name
                    break

        if not url_property_name:
            print(f"  ⚠️  URLプロパティが見つかりません")
            return False

        # URLプロパティを更新
        payload = {"properties": {url_property_name: {"url": spotify_url}}}

        response = requests.patch(page_url, headers=HEADERS, json=payload)

        if response.status_code == 200:
            return True
        else:
            print(f"  ❌ URLプロパティの更新に失敗: {response.status_code}")
            return False

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return False


def main():
    """メイン処理"""
    print("🎵 Notionエピソードのカバー画像を更新します（拡張版）...\n")
    print(f"📌 データベースID: {DATABASE_ID}\n")

    pages = get_database_pages()
    print(f"✅ {len(pages)}件のエピソードが見つかりました\n")

    updated_count = 0
    url_updated_count = 0
    skipped_count = 0
    failed_count = 0
    already_has_cover = 0

    for i, page in enumerate(pages, 1):
        page_id = page.get("id", "")
        title = get_page_title(page)
        existing_cover = page.get("cover")
        spotify_url = extract_spotify_url_from_page(page)

        print(f"[{i}/{len(pages)}] {title[:60]}...")

        # Podcastプロパティから番組名を取得
        props = page.get("properties", {})
        podcast_name = None
        for prop_name in ["Podcast", "podcast", "番組", "Show"]:
            if prop_name in props:
                prop = props[prop_name]
                if prop.get("type") == "select":
                    select_value = prop.get("select")
                    if select_value:
                        podcast_name = select_value.get("name", "")
                break
        
        # 再処理が必要な番組（Takram Cast、ミモリラジオ、STEAM.fm）
        needs_reprocessing = False
        if podcast_name:
            needs_reprocessing = (
                "Takram Cast" in podcast_name
                or "ミモリラジオ" in podcast_name
                or "STEAM.fm" in podcast_name
            )
        
        # タイトルベースの判定も残す（Takram Cast用）
        is_takram = (
            "takram" in title.lower()
            or "データとデザイン" in title
            or "デザインエンジニアリング" in title
            or ("デザイン" in title and "エンジニア" in title)
        )
        
        needs_reprocessing = needs_reprocessing or is_takram

        # 既存のカバー画像が番組カバー（番組のデフォルト画像）かどうかを判定
        is_show_cover = False
        if existing_cover:
            cover_url = ""
            if existing_cover.get("type") == "external":
                cover_url = existing_cover.get("external", {}).get("url", "")
            # 番組カバー画像の特徴的なハッシュ部分で判定
            # Takram Castの番組カバーは "8cf1ff631fdba63c7a35" を含む
            if cover_url and "8cf1ff631fdba63c7a35" in cover_url:
                is_show_cover = True
                print(
                    f"  🔍 番組カバー画像を検出しました（エピソード固有画像で更新）"
                )

        # カバー画像がない、または再処理が必要なエピソードの場合のみ処理
        if existing_cover and not needs_reprocessing and not is_show_cover:
            print(f"  ℹ️  既にカバー画像が設定されています（スキップ）")
            already_has_cover += 1
            continue

        if existing_cover and (needs_reprocessing or is_show_cover):
            reason = []
            if needs_reprocessing:
                reason.append(f"番組: {podcast_name or 'タイトルベース'}")
            if is_show_cover:
                reason.append("番組カバー検出")
            print(
                f"  🔄 エピソード固有画像で再処理します（{' / '.join(reason)}）"
            )

        # URLがない場合は検索して取得
        if not spotify_url:
            print(f"  ⏭️  Spotify URLが見つかりませんでした")
            print(f"  🔍 エピソード名でSpotify検索中...")

            spotify_url = search_episode_url_by_title(title)

            if spotify_url:
                print(f"  ✅ Spotify URLを取得しました")
                # NotionページのURLプロパティを更新
                if update_notion_page_url(page_id, spotify_url):
                    print(f"  ✅ URLプロパティを更新しました")
                    url_updated_count += 1
                else:
                    print(f"  ⚠️  URLプロパティの更新に失敗しましたが、続行します")
            else:
                print(f"  ⚠️  Spotify URLが見つかりませんでした（スキップ）")
                skipped_count += 1
                continue

        print(f"  🔗 Spotify URL: {spotify_url}")

        # カバー画像URLを取得
        print(f"  🖼️  カバー画像を取得中...")
        cover_url = None

        # まず通常の方法を試す（episode_titleを渡す）
        cover_url = extract_episode_cover_from_spotify_page(
            spotify_url, episode_title=title
        )

        # 通常の方法で失敗した場合、Listen Notes APIを試す
        if not cover_url and LISTEN_NOTES_API_AVAILABLE:
            print(f"  🔄 Listen Notes APIでエピソードを検索中...")
            cover_url = get_cover_image_from_listen_notes(title)

        # それでも取得できない場合、ブラウザ操作を試す
        if not cover_url:
            print(f"  🔄 ブラウザ操作で画像URLを取得します...")
            cover_url = get_cover_image_with_browser_mcp(spotify_url)

        # それでも取得できない場合、エピソード名で再検索して番組カバーを取得
        if not cover_url:
            print(f"  🔄 エピソード名で再検索して番組カバー画像を取得します...")
            # エピソード名でSpotify検索して番組情報を取得
            if SPOTIFY_API_AVAILABLE:
                try:
                    spotify_client = SpotifyClient()
                    # エピソード名の一部で検索
                    search_query = title[:50]
                    results = spotify_client.sp.search(
                        q=search_query, type="episode", limit=3
                    )

                    if results["episodes"]["items"]:
                        # 最初の結果から番組情報を取得
                        episode = results["episodes"]["items"][0]
                        show = episode.get("show", {})
                        if show and show.get("images"):
                            cover_url = show["images"][0]["url"]
                            print(f"  ✅ 検索結果から番組カバー画像を取得しました")
                except Exception as e:
                    print(f"  ⚠️  再検索エラー: {e}")

        if not cover_url:
            print(f"  ⚠️  カバー画像の取得に失敗（スキップ）")
            failed_count += 1
            continue

        print(f"  ✅ カバー画像URL: {cover_url[:60]}...")

        # Notionページのカバー画像を更新
        print(f"  📝 Notionページを更新中...")
        if update_notion_page_cover(page_id, cover_url):
            print(f"  ✅ 更新完了！")
            updated_count += 1
        else:
            failed_count += 1

        time.sleep(1)
        print()

    # 結果を表示
    print("\n" + "=" * 60)
    print("📊 処理結果")
    print("=" * 60)
    print(f"✅ カバー画像更新成功: {updated_count}件")
    print(f"🔗 URL更新成功: {url_updated_count}件")
    print(f"ℹ️  既にカバー画像あり（スキップ）: {already_has_cover}件")
    print(f"⏭️  処理不可（URL取得失敗）: {skipped_count}件")
    print(f"❌ 失敗: {failed_count}件")
    print(f"📋 合計: {len(pages)}件")
    print("=" * 60)


if __name__ == "__main__":
    main()
