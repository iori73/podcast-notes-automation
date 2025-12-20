#!/usr/bin/env python3
"""
生成されたMarkdownファイルをNotionにアップロードするスクリプト
"""

import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent / "src"))

from integrations.notion_client import NotionClient
from spotify import SpotifyClient


def upload_episode_to_notion(md_file_path: str, spotify_url: str = None):
    """エピソードのMarkdownファイルをNotionにアップロード"""
    try:
        md_file = Path(md_file_path)
        if not md_file.exists():
            print(f"❌ ファイルが見つかりません: {md_file_path}")
            return False
        
        # Markdownファイルの内容を読み込む
        with open(md_file, "r", encoding="utf-8") as f:
            markdown_content = f.read()
        
        # タイトルをファイル名から取得
        episode_title = md_file.parent.name  # ディレクトリ名がタイトル
        
        print(f"📝 Notionにアップロード中: {episode_title}")
        
        # Spotify URLからメタデータを取得（提供されている場合）
        cover_url = None
        podcast_name = None
        release_date = None
        duration_minutes = None
        
        if spotify_url:
            try:
                spotify_client = SpotifyClient()
                episode_info = spotify_client.get_episode_info(spotify_url)
                cover_url = episode_info.get("cover_image_url", "")
                podcast_name = episode_info.get("show_name", "")
                release_date = episode_info.get("release_date", "")  # YYYY-MM-DD形式
                duration_ms = episode_info.get("duration_ms", 0)
                duration_minutes = duration_ms / (1000 * 60) if duration_ms > 0 else None
                
                print(f"✅ カバー画像URLを取得: {cover_url[:50]}..." if cover_url else "⚠️ カバー画像が見つかりませんでした")
                print(f"✅ ポッドキャスト名: {podcast_name}")
                print(f"✅ 公開日: {release_date}")
                print(f"✅ 再生時間: {duration_minutes:.1f}分" if duration_minutes else "⚠️ 再生時間が見つかりませんでした")
            except Exception as e:
                print(f"⚠️ Spotify情報の取得に失敗: {str(e)}")
        
        # Notionクライアントを初期化
        notion = NotionClient()
        
        # Notionにページを作成
        page_id = notion.create_page(
            title=episode_title,
            markdown_content=markdown_content,
            spotify_url=spotify_url,
            cover_url=cover_url if cover_url else None,
            podcast_name=podcast_name if podcast_name else None,
            release_date=release_date if release_date else None,
            duration_minutes=duration_minutes if duration_minutes else None,
        )
        
        if page_id:
            print(f"✅ Notionへのアップロードが完了しました！")
            return True
        else:
            print(f"❌ Notionへのアップロードに失敗しました")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メイン処理"""
    if len(sys.argv) < 2:
        print("使用方法: python upload_to_notion.py <markdown_file_path> [spotify_url]")
        print("\n例:")
        print('  python upload_to_notion.py "data/outputs/エピソード名/episode_summary.md" "https://open.spotify.com/episode/..."')
        sys.exit(1)
    
    md_file_path = sys.argv[1]
    spotify_url = sys.argv[2] if len(sys.argv) > 2 else None
    
    upload_episode_to_notion(md_file_path, spotify_url)


if __name__ == "__main__":
    main()

