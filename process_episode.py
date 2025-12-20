#!/usr/bin/env python3
"""
指定されたSpotify URLのエピソードを処理するスクリプト
"""

import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent / "src"))

from spotify import SpotifyClient
from listen_notes import ListenNotesClient
from summary_fm import SummaryFMProcessor
from integrations.notion_client import NotionClient
from datetime import datetime


def process_episode(spotify_url: str):
    """Spotify URLからエピソードを処理"""
    try:
        print(f"🎧 エピソード処理を開始します: {spotify_url}\n")

        # **Spotifyからメタデータを取得**
        print("📡 Spotifyからエピソード情報を取得中...")
        spotify_client = SpotifyClient()
        episode_info = spotify_client.get_episode_info(spotify_url)
        title = episode_info["title"]
        print(f"✅ タイトル: {title}")
        print(f"   番組: {episode_info.get('show_name', 'N/A')}")
        print(f"   公開日: {episode_info.get('release_date', 'N/A')}")

        # **言語を検出**
        language = episode_info.get("language", "ja").split("-")[0]  # "en-US" → "en"
        ln_language = "English" if language == "en" else "Japanese"
        print(f"🌍 検出された言語: {ln_language}\n")

        # **Listen Notes クライアントを初期化**
        print("🔍 Listen Notesでエピソードを検索中...")
        ln_client = ListenNotesClient()
        ln_client.set_language(ln_language)

        # **Listen Notes でエピソード URL を取得**
        ln_url = ln_client.get_episode_url(title)
        if ln_url:
            print(f"✅ Listen Notes URL: {ln_url}")
        else:
            print("⚠️ Listen Notesでエピソードが見つかりませんでした")

        # **MP3ファイルのダウンロード**
        downloaded_file = None
        if ln_url:
            try:
                print("\n📥 音声ファイルをダウンロード中...")
                downloaded_file = ln_client.download_episode(
                    episode_url=ln_url, episode_title=title
                )
                print(f"✅ Listen Notesからダウンロード成功: {downloaded_file}")
            except Exception as e:
                print(f"❌ Listen Notes ダウンロードエラー: {str(e)}")

        # **Listen Notesで見つからなかった場合は Spotify からダウンロード**
        if not downloaded_file:
            print("\n⚠️ Listen Notesでエピソードが見つかりませんでした。")
            print("📥 代わりにSpotifyから直接ダウンロードを試みます...")
            try:
                # Spotifyからの直接ダウンロード機能があるか確認
                if hasattr(spotify_client, 'download_episode'):
                    downloaded_file = spotify_client.download_episode(spotify_url)
                    print(f"✅ Spotifyからダウンロード成功: {downloaded_file}")
                else:
                    print("❌ Spotifyからの直接ダウンロード機能が実装されていません")
                    print("💡 ローカルにMP3ファイルがある場合は、そのパスを指定してください")
                    sys.exit(1)
            except Exception as e:
                print(f"❌ Spotify ダウンロードエラー: {str(e)}")
                sys.exit(1)  # Spotifyでも取得できない場合は終了

        # **MP3 ファイルのメタデータを取得**
        duration = f"{episode_info['duration_ms'] // (1000 * 60)}:{(episode_info['duration_ms'] // 1000) % 60:02d}"
        release_date = datetime.strptime(
            episode_info["release_date"], "%Y-%m-%d"
        ).strftime("%Y年%m月%d日")

        # **文字起こし処理（SummaryFMProcessorを使用）**
        print("\n🤖 Summary.fmで文字起こし・要約処理を開始します...")
        print("⏳ この処理には時間がかかる場合があります（最大20分）...\n")
        
        summary_processor = SummaryFMProcessor()
        try:
            results = summary_processor.process_audio(
                mp3_path=str(downloaded_file),
                spotify_url=spotify_url,
                release_date=release_date,
                duration=duration,
                language=ln_language,
            )
            print("\n✅ 処理が完了しました！")
            print(f"📄 結果は data/outputs/ に保存されました")
            print(f"📝 文字起こし: {len(results.get('transcription', ''))} 文字")
            print(f"📝 要約: {len(results.get('summary', ''))} 文字")
            print(f"📝 タイムスタンプ: {len(results.get('timestamps', ''))} 文字")
            
            # **Notionへのアップロード（オプション）**
            try:
                from utils import load_config
                config = load_config()
                notion_config = config.get("notion", {})
                
                if notion_config.get("api_key") and notion_config.get("database_id"):
                    print("\n📝 Notionへのアップロードを開始します...")
                    
                    # 生成されたMarkdownファイルを読み込む
                    output_dir = Path("data/outputs") / title
                    md_file = output_dir / "episode_summary.md"
                    
                    if md_file.exists():
                        with open(md_file, "r", encoding="utf-8") as f:
                            markdown_content = f.read()
                        
                        # Notionクライアントを初期化
                        notion = NotionClient()
                        
                        # カバー画像URLを取得
                        cover_url = episode_info.get("cover_image_url", "")
                        
                        # Notionにページを作成
                        page_id = notion.create_page(
                            title=title,
                            markdown_content=markdown_content,
                            spotify_url=spotify_url,
                            cover_url=cover_url if cover_url else None,
                            podcast_name=episode_info.get("show_name", "")
                        )
                        
                        if page_id:
                            print("✅ Notionへのアップロードが完了しました！")
                        else:
                            print("⚠️ Notionへのアップロードに失敗しました")
                    else:
                        print(f"⚠️ Markdownファイルが見つかりません: {md_file}")
                else:
                    print("\n💡 Notion APIキーが設定されていないため、Notionへのアップロードをスキップします")
            except Exception as e:
                print(f"\n⚠️ Notionアップロードエラー: {str(e)}")
                print("   処理は完了していますが、Notionへのアップロードに失敗しました")
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"\n❌ SummaryFMProcessor エラー: {str(e)}")
            print("⚠️ 音声処理に失敗しました")
            import traceback
            traceback.print_exc()
        finally:
            summary_processor.cleanup()

    except Exception as e:
        print(f"\n❌ エラー発生: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # コマンドライン引数からURLを取得、なければデフォルトURLを使用
    if len(sys.argv) > 1:
        spotify_url = sys.argv[1]
    else:
        # デフォルトURL（ユーザーが指定したURL）
        spotify_url = "https://open.spotify.com/episode/47txLShMhtgGGJZz1PnMqC?si=a4e3d5eba21640a6"
    
    process_episode(spotify_url)

