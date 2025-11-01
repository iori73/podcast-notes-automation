from spotify import SpotifyClient
from listen_notes import ListenNotesClient
from summary_fm import SummaryFMProcessor
from datetime import datetime
import sys


def test_podcast_fetch():
    # spotify_url = "https://open.spotify.com/episode/47mtYSQzPfGwlGLJ4bPw5b?si=74c4815802524006&nd=1&dlsi=782d36f54f874c79"
    # spotify_url = "https://open.spotify.com/episode/6S4oCZn4I9H53QyFZBMcYp?si=233184cd01344b04"

    # spotify_url = "https://open.spotify.com/episode/00PdTxtWodY9vGZQwswULK?si=7b0c3819a0ae45af" 67
    # spotify_url = "https://open.spotify.com/episode/0uwLUUmE1ukUtnobkNm063?si=10e1293d73d04205" 68
    spotify_url = (
        "https://open.spotify.com/episode/3yvAS5sQAVmdIcIslWWhs1?si=ec2e32bdd9294085"
    )

    try:
        # **Spotifyからメタデータを取得**
        spotify_client = SpotifyClient()
        episode_info = spotify_client.get_episode_info(spotify_url)
        title = episode_info["title"]
        print(f"🎧 Spotifyエピソード情報: {title}")

        # **言語を検出**
        language = episode_info.get("language", "ja").split("-")[0]  # "en-US" → "en"
        ln_language = "English" if language == "en" else "Japanese"
        print(f"🌍 検出された言語: {ln_language}")

        # **Listen Notes クライアントを初期化**
        ln_client = ListenNotesClient()
        ln_client.set_language(ln_language)

        # **Listen Notes でエピソード URL を取得**
        ln_url = ln_client.get_episode_url(title)
        print(f"🔗 Listen Notes URL: {ln_url}")

        # **MP3ファイルのダウンロード**
        downloaded_file = None
        if ln_url:
            try:
                downloaded_file = ln_client.download_episode(
                    episode_url=ln_url, episode_title=title
                )
                print(f"✅ Listen Notesからダウンロード成功: {downloaded_file}")
            except Exception as e:
                print(f"❌ Listen Notes ダウンロードエラー: {str(e)}")

        # **Listen Notesで見つからなかった場合は Spotify からダウンロード**
        if not downloaded_file:
            print("⚠️ Listen Notesでエピソードが見つかりませんでした。")
            print("📥 代わりにSpotifyから直接ダウンロードします。")
            try:
                downloaded_file = spotify_client.download_episode(spotify_url)
                print(f"✅ Spotifyからダウンロード成功: {downloaded_file}")
            except Exception as e:
                print(f"❌ Spotify ダウンロードエラー: {str(e)}")
                sys.exit(1)  # Spotifyでも取得できない場合は終了

        # **MP3 ファイルのメタデータを取得**
        duration = f"{episode_info['duration_ms'] // (1000 * 60)}:{(episode_info['duration_ms'] // 1000) % 60:02d}"
        release_date = datetime.strptime(
            episode_info["release_date"], "%Y-%m-%d"
        ).strftime("%Y年%m月%d日")

        # **文字起こし処理（SummaryFMProcessorを使用）**
        print("🤖 SummaryFM音声処理を開始します...")
        summary_processor = SummaryFMProcessor()
        try:
            results = summary_processor.process_audio(
                mp3_path=downloaded_file,
                spotify_url=spotify_url,
                release_date=release_date,
                duration=duration,
                language=ln_language,
            )
            print("🔍 取得結果:", results)
        except Exception as e:
            print(f"❌ SummaryFMProcessor エラー: {str(e)}")
            print("⚠️ 音声処理に失敗しました")
        finally:
            summary_processor.cleanup()

    except Exception as e:
        print(f"❌ エラー発生: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    test_podcast_fetch()
