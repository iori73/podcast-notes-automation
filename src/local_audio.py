



# # src/local_audio.py
from summary_fm import SummaryFMProcessor
from pathlib import Path
from datetime import datetime
from mutagen.mp3 import MP3
import re

class LocalAudioProcessor:
    def __init__(self):
        self.summary_processor = SummaryFMProcessor()

    def get_audio_duration(self, file_path):
        """MP3ファイルの長さを取得"""
        try:
            audio = MP3(file_path)
            seconds = int(audio.info.length)
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}:{remaining_seconds:02d}"
        except Exception as e:
            print(f"長さの取得に失敗: {str(e)}")
            return ""

    def detect_language_from_title(self, mp3_path):
        """MP3 のタイトルから言語を判定"""
        title = Path(mp3_path).stem  # "Essentials How Hormones Shape Sexual Development"

        if re.search(r"[a-zA-Z]", title):  # アルファベットが含まれていれば英語とみなす
            print(f"タイトルの言語判定: English ({title})")
            return "English"
        else:
            print(f"タイトルの言語判定: Japanese ({title})")
            return "Japanese"



    # def process_local_audio(self, mp3_path, metadata=None, language=None):

    # def process_local_audio(self, mp3_path, metadata=None, language=None):
    #     try:
    #         # MP3ファイルの存在確認
    #         audio_file = Path(mp3_path)
    #         if not audio_file.exists():
    #             raise FileNotFoundError(f"File not found: {mp3_path}")

    #         # 言語が未指定の場合、タイトルから判定
    #         if language is None:
    #             language = self.detect_language_from_title(mp3_path)

    #         # メタデータがない場合はファイル情報から生成
    #         if metadata is None:
    #             duration = self.get_audio_duration(mp3_path)
    #             metadata = {
    #                 "title": audio_file.stem,
    #                 "release_date": datetime.fromtimestamp(audio_file.stat().st_mtime).strftime('%Y年%m月%d日'),
    #                 "duration": duration
    #             }

    #         print(f"📢 処理開始: {audio_file} (言語: {language})")

    #         # Summary.fm処理を実行
    #         results = self.summary_processor.process_audio(
    #             mp3_path=str(audio_file),  # MP3ファイルのパスを渡す
    #             spotify_url=None,
    #             release_date=metadata.get("release_date", ""),
    #             duration=metadata.get("duration", ""),
    #             language=language  # 言語を渡す
    #         )

    #         print(f"✅ 処理成功: {audio_file}")
    #         return results

    #     except Exception as e:
    #         print(f"❌ ローカルファイル処理エラー: {str(e)}")
    #         raise

    #     try:
    #         # MP3ファイルの存在確認
    #         audio_file = Path(mp3_path)
    #         if not audio_file.exists():
    #             raise FileNotFoundError(f"File not found: {mp3_path}")

    #         # 言語が未指定の場合、タイトルから判定
    #         if language is None:
    #             language = self.detect_language_from_title(mp3_path)

    #         # メタデータがない場合はファイル情報から生成
    #         if metadata is None:
    #             duration = self.get_audio_duration(mp3_path)
    #             metadata = {
    #                 "title": audio_file.stem,
    #                 "release_date": datetime.fromtimestamp(audio_file.stat().st_mtime).strftime('%Y年%m月%d日'),
    #                 "duration": duration
    #             }

    #         # Summary.fm処理を実行
    #         results = self.summary_processor.process_audio(
    #             mp3_path=str(audio_file),  # MP3ファイルのパスを渡す
    #             spotify_url=None,
    #             release_date=metadata.get("release_date", ""),
    #             duration=metadata.get("duration", ""),
    #             language=language  # 言語を渡す
    #         )

    #         return results

    #     except Exception as e:
    #         print(f"ローカルファイル処理エラー: {str(e)}")
    #         raise

    def process_local_audio(self, mp3_path, metadata=None, language=None):
        try:
            # MP3ファイルの存在確認
            audio_file = Path(mp3_path)
            if not audio_file.exists():
                raise FileNotFoundError(f"File not found: {mp3_path}")

            # 言語が未指定の場合、タイトルから判定
            if language is None:
                language = self.detect_language_from_title(mp3_path)

            # メタデータがない場合はファイル情報から生成
            if metadata is None:
                duration = self.get_audio_duration(mp3_path)
                metadata = {
                    "title": audio_file.stem,
                    "release_date": datetime.fromtimestamp(audio_file.stat().st_mtime).strftime('%Y年%m月%d日'),
                    "duration": duration
                }

            print(f"📢 処理開始: {audio_file} (言語: {language})")

            # Summary.fm処理を実行
            results = self.summary_processor.process_audio(
                mp3_path=str(audio_file),  # MP3ファイルのパスを渡す
                spotify_url=None,
                release_date=metadata.get("release_date", ""),
                duration=metadata.get("duration", ""),
                language=language  # 言語を渡す
            )

            print(f"✅ 処理成功: {audio_file}")
            return results

        except Exception as e:
            print(f"❌ ローカルファイル処理エラー: {str(e)}")
            raise
