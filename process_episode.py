#!/usr/bin/env python3
"""
指定されたSpotify URLのエピソードを処理するスクリプト
"""

import sys
import re
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
        
        # 番組名を取得
        show_name = episode_info.get('show_name', '')

        # **Listen Notes でエピソード URL を取得**
        # 番組名を含めて検索（より正確なマッチング）
        print(f"   番組名: {show_name}, タイトル: {title}")
        episode = ln_client.search_episode(title, show_name=show_name)
        ln_url = episode.get('listennotes_url') if episode else None
        
        # 見つからない場合、タイトルの主要部分で再検索
        if not ln_url and '：' in title:
            title_part = title.split('：')[0]
            print(f"   タイトルの主要部分で再検索: {title_part}")
            episode = ln_client.search_episode(title_part, show_name=show_name)
            if episode:
                ln_url = episode.get('listennotes_url')
        
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
                
                # **Download Verification**
                print("🔍 ダウンロードファイルを検証中...")
                verification = ln_client.verify_download(
                    downloaded_file, 
                    expected_duration_ms=episode_info.get('duration_ms')
                )
                
                if not verification['valid']:
                    print(f"❌ ファイル検証失敗: {verification['error']}")
                    print("   ダウンロードしたファイルは無効です。ローカルファイルを検索します。")
                    # Delete invalid file
                    Path(downloaded_file).unlink(missing_ok=True)
                    downloaded_file = None
                else:
                    file_size_mb = verification['file_size'] / 1024 / 1024
                    print(f"✅ ファイル検証成功: {file_size_mb:.1f}MB, MP3形式: {verification['is_mp3']}")
                    if verification['duration_match'] == False:
                        print("   ⚠️ ファイルの長さが予想と異なります（内容を確認してください）")
                        
            except Exception as e:
                print(f"❌ Listen Notes ダウンロードエラー: {str(e)}")

        # **Listen Notesで見つからなかった場合は ローカルファイルを検索**
        if not downloaded_file:
            print("\n⚠️ Listen Notesでエピソードが見つかりませんでした。")
            print("📁 ローカルのダウンロードディレクトリを検索中...")
            
            # ローカルのダウンロードディレクトリを検索
            downloads_dir = Path("data/downloads")
            if downloads_dir.exists():
                # タイトルからキーワードを抽出（より正確なマッチングのため）
                # まず、タイトルの主要部分を抽出（「：」で分割）
                title_parts = []
                if '：' in title:
                    title_parts = [part.strip() for part in title.split('：')]
                else:
                    title_parts = [title]
                
                # タイトルから主要なキーワードを抽出（日本語文字のみ）
                keywords = re.findall(r'[\u4e00-\u9fff]+', title)
                # 長いキーワードを優先（3文字以上）
                keywords = [kw for kw in keywords if len(kw) >= 3]
                # 長さでソート（長い順）
                keywords = sorted(keywords, key=len, reverse=True)
                
                # タイトルの主要部分を優先的に追加
                search_terms = title_parts + keywords[:3]  # タイトル部分 + 上位3つのキーワード
                
                print(f"   検索キーワード: {search_terms[:5]}")  # 上位5つを表示
                
                # Normalize show_name for comparison
                def normalize_name(name):
                    """Normalize name for comparison (lowercase, remove spaces/punctuation)"""
                    if not name:
                        return ""
                    return re.sub(r'[^\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', '', name.lower())
                
                normalized_show_name = normalize_name(show_name)
                
                best_match = None
                best_score = 0
                MIN_SCORE_THRESHOLD = 15  # Increased threshold for safety
                
                for mp3_file in downloads_dir.glob("*.mp3"):
                    file_name = mp3_file.name
                    file_stem = mp3_file.stem  # Filename without extension
                    normalized_file_name = normalize_name(file_stem)
                    score = 0
                    match_reasons = []
                    
                    # Priority 1: Exact title match (highest priority)
                    if title.strip() == file_stem or title.strip() in file_stem:
                        score += 100
                        match_reasons.append("完全タイトル一致")
                    
                    # Priority 2: Show name in filename (REQUIRED if show_name is provided)
                    show_name_in_file = False
                    if normalized_show_name and normalized_show_name in normalized_file_name:
                        score += 50
                        show_name_in_file = True
                        match_reasons.append("番組名含む")
                    
                    # Priority 3: Title parts match
                    parts_matched = 0
                    for part in title_parts:
                        if part and len(part) >= 3 and part in file_name:
                            score += len(part) * 2
                            parts_matched += 1
                    if parts_matched > 0:
                        match_reasons.append(f"タイトル部分{parts_matched}個一致")
                    
                    # Priority 4: Keywords match (require multiple keywords)
                    keywords_matched = 0
                    for keyword in keywords[:5]:
                        if keyword in file_name:
                            score += len(keyword)
                            keywords_matched += 1
                    if keywords_matched > 0:
                        match_reasons.append(f"キーワード{keywords_matched}個一致")
                    
                    # STRICT: If show_name is provided, file MUST contain show_name OR exact title
                    if normalized_show_name and not show_name_in_file:
                        if score < 100:  # Not an exact title match
                            # Skip files that don't have show name (likely wrong podcast)
                            continue
                    
                    # Log candidates with non-zero scores
                    if score > 0:
                        print(f"   候補: {file_name} (スコア: {score}, 理由: {', '.join(match_reasons)})")
                    
                    if score > best_score:
                        best_score = score
                        best_match = mp3_file
                
                # スコアが一定以上の場合のみ使用（閾値を引き上げ）
                if best_match and best_score >= MIN_SCORE_THRESHOLD:
                    downloaded_file = best_match
                    print(f"✅ ローカルファイルが見つかりました: {downloaded_file} (マッチスコア: {best_score})")
                    
                    # Verify local file too
                    verification = ln_client.verify_download(
                        downloaded_file, 
                        expected_duration_ms=episode_info.get('duration_ms')
                    )
                    if not verification['valid']:
                        print(f"⚠️ ローカルファイル検証警告: {verification['error']}")
                    elif verification['duration_match'] == False:
                        print("   ⚠️ ファイルの長さが予想と異なります（内容を確認してください）")
                else:
                    print(f"⚠️ ローカルファイルが見つかりませんでした (最高スコア: {best_score}, 必要スコア: {MIN_SCORE_THRESHOLD})")
            
            if not downloaded_file:
                print("❌ ローカルにMP3ファイルが見つかりませんでした")
                print("💡 以下のいずれかの方法で音声ファイルを取得してください:")
                print("   1. data/downloads/ ディレクトリにMP3ファイルを配置")
                print(f"   2. ファイル名にタイトルの主要部分を含める: {title_parts[0] if 'title_parts' in locals() and title_parts else 'タイトルの一部'}")
                sys.exit(1)

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

