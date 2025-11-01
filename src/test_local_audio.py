# # # # src/test_local_audio.py
# # # from local_audio import LocalAudioProcessor

# # # def test_local_audio():
# # #     processor = LocalAudioProcessor()

# # #     # テスト用のメタデータ
# # #     metadata = {
# # #         "title": "テストエピソード",
# # #         "release_date": "2024年1月1日",
# # #         "duration": "30:00"
# # #     }

# # #     # MP3ファイルのパスを指定して処理
# # #     results = processor.process_local_audio(
# # #         "path/to/your/audio.mp3",
# # #         metadata=metadata
# # #     )

# # #     if results:
# # #         print("\n=== 文字起こし ===")
# # #         print(results["transcription"][:200] + "...")

# # #         print("\n=== 要約 ===")
# # #         print(results["summary"])

# # #         print("\n=== タイムスタンプ ===")
# # #         print(results["timestamps"])

# # # if __name__ == "__main__":
# # #     test_local_audio()


# # # src/test_local_audio.py
# # from local_audio import LocalAudioProcessor
# # from pathlib import Path


# # def test_local_audio():
# #     processor = LocalAudioProcessor()

# #     # 対象のMP3ファイルのパス
# #     mp3_path = Path(
# #         "downloads/#21 Amazon退職後に医学部進学予定…が、3ヶ月でTwitter社に転職！？驚きのアメリカ流キャリア選択.mp3"
# #     )

# #     # MP3ファイルのパスを指定して処理
# #     results = processor.process_local_audio(str(mp3_path))

# #     if results:
# #         print("\n=== 文字起こし ===")
# #         print(results["transcription"][:200] + "...")

# #         print("\n=== 要約 ===")
# #         print(results["summary"])

# #         print("\n=== タイムスタンプ ===")
# #         print(results["timestamps"])


# # if __name__ == "__main__":
# #     test_local_audio()


# # # # src/test_local_audio.py

# # これはpoutputsのfolderにtemp_は残る
# # from local_audio import LocalAudioProcessor
# # from pathlib import Path
# # import shutil


# # def test_local_audio():
# #     processor = LocalAudioProcessor()

# #     # 対象のMP3ファイルのパス
# #     original_mp3_path = Path(
# #         "downloads/マンガとポンチ絵【第216号音声版】.mp3"
# #     )

# #     # ファイルの存在確認
# #     if not original_mp3_path.exists():
# #         raise FileNotFoundError(f"File not found: {original_mp3_path}")

# #     try:
# #         # 一時的な名前でファイルをコピー
# #         temp_mp3_path = original_mp3_path.parent / f"temp_{original_mp3_path.stem}.mp3"
# #         shutil.copy2(original_mp3_path, temp_mp3_path)
# #         print(f"Processing file: {temp_mp3_path}")

# #         # 一時ファイルを使用して処理
# #         results = processor.process_local_audio(str(temp_mp3_path))

# #         if results:
# #             print("\n=== 文字起こし ===")
# #             print(results["transcription"][:200] + "...")

# #             print("\n=== 要約 ===")
# #             print(results["summary"])

# #             print("\n=== タイムスタンプ ===")
# #             print(results["timestamps"])

# #     finally:
# #         # 一時ファイルを削除
# #         if temp_mp3_path.exists():
# #             temp_mp3_path.unlink()
# #             print("Temporary file cleaned up")


# # if __name__ == "__main__":
# #     test_local_audio()


# # # # src/test_local_audio.py
# from local_audio import LocalAudioProcessor
# from pathlib import Path


# def test_local_audio():
#     processor = LocalAudioProcessor()

#     # 対象のMP3ファイルのパス
#     mp3_path = Path(
#         "downloads/How this weekend’s ‘Tesla Takeover’ protests against Elon Musk came together on Bluesky.mp3"
#     )  # ダウンロードしたMP3ファイルのパスを指定

#     # ファイルの存在確認
#     if not mp3_path.exists():
#         raise FileNotFoundError(f"File not found: {mp3_path}")

#     print(f"Processing file: {mp3_path}")

#     # MP3ファイルのパスを指定して処理
#     results = processor.process_local_audio(str(mp3_path))

#     if results:
#         print("\n=== 文字起こし ===")
#         print(results["transcription"][:200] + "...")

#         print("\n=== 要約 ===")
#         print(results["summary"])

#         print("\n=== タイムスタンプ ===")
#         print(results["timestamps"])


# if __name__ == "__main__":
#     test_local_audio()


# def process_local_audio():
#     # 1. ローカル音声ファイルのパスを指定
#     mp3_path = Path("downloads/podcast_name.mp3")

#     # 2. ローカル音声処理クラスの初期化
#     processor = LocalAudioProcessor()

#     # 3. 音声処理と要約生成
#     results = processor.process_local_audio(str(mp3_path))





# # src/test_local_audio.py
# from local_audio import LocalAudioProcessor

# def test_local_audio():
#     processor = LocalAudioProcessor()
    
#     # テスト用のメタデータ
#     metadata = {
#         "title": "テストエピソード",
#         "release_date": "2024年1月1日",
#         "duration": "30:00"
#     }
    
#     # MP3ファイルのパスを指定して処理
#     results = processor.process_local_audio(
#         "path/to/your/audio.mp3",
#         metadata=metadata
#     )
    
#     if results:
#         print("\n=== 文字起こし ===")
#         print(results["transcription"][:200] + "...")
        
#         print("\n=== 要約 ===")
#         print(results["summary"])
        
#         print("\n=== タイムスタンプ ===")
#         print(results["timestamps"])

# if __name__ == "__main__":
#     test_local_audio()








# # src/test_local_audio.py
# from local_audio import LocalAudioProcessor
# from pathlib import Path

# def test_local_audio():
#     processor = LocalAudioProcessor()
    
#     # 対象のMP3ファイルのパス
#     mp3_path = Path("downloads/Essentials How Hormones Shape Sexual Development.mp3")
    
#     # MP3ファイルのパスを指定して処理
#     results = processor.process_local_audio(str(mp3_path))
    
#     if results:
#         print("\n=== 文字起こし ===")
#         print(results["transcription"][:200] + "...")
        
#         print("\n=== 要約 ===")
#         print(results["summary"])
        
#         print("\n=== タイムスタンプ ===")
#         print(results["timestamps"])

# if __name__ == "__main__":
#     test_local_audio()






# src/test_local_audio.py
from local_audio import LocalAudioProcessor
from pathlib import Path
import re

# def detect_language_from_title(mp3_path):
#     """MP3 のタイトルから言語を判定"""
#     title = mp3_path.stem  # "Essentials How Hormones Shape Sexual Development"

#     # **英語のタイトルか判定**
#     if re.search(r"[a-zA-Z]", title):  # アルファベットが含まれていれば英語とみなす
#         print(f"タイトルの言語判定: English ({title})")
#         return "English"
#     else:
#         print(f"タイトルの言語判定: Japanese ({title})")
#         return "Japanese"

def detect_language_from_title(mp3_path):
    """MP3 のタイトルから言語を判定"""
    title = mp3_path.stem  # ファイル名から拡張子を除いたタイトルを取得

    # **日本語が含まれているか判定**
    if re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", title):  # ひらがな・カタカナ・漢字を含むなら日本語
        print(f"タイトルの言語判定: Japanese ({title})")
        return "Japanese"
    else:
        print(f"タイトルの言語判定: English ({title})")
        return "English"



def test_local_audio():
    processor = LocalAudioProcessor()

    # 対象のMP3ファイルのパス
    # プロジェクトルートからの絶対パスを使用
    project_root = Path(__file__).parent.parent
    mp3_path = project_root / "data" / "downloads" / "傾聴と伝え方の本「まず、ちゃんと聴く。」を読んだ感想.mp3"  # 先頭にスペースがある

    # **MP3タイトルから言語を判定**
    # language = detect_language_from_title(mp3_path)
    # この音声は実際には日本語なので、明示的に日本語を指定
    language = "Japanese"

    # MP3ファイルのパスを指定して処理
    results = processor.process_local_audio(str(mp3_path), language=language)  # 言語を渡す

    if results:
        print("\n=== 文字起こし ===")
        print(results["transcription"][:200] + "...")
        
        print("\n=== 要約 ===")
        print(results["summary"])
        
        print("\n=== タイムスタンプ ===")
        print(results["timestamps"])

if __name__ == "__main__":
    test_local_audio()
