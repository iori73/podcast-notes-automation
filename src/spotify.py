# # src/spotify.py
# import spotipy
# from spotipy.oauth2 import SpotifyClientCredentials
# from utils import load_config
# import re
# from datetime import datetime


# class SpotifyClient:
#     def __init__(self):
#         config = load_config()
#         auth_manager = SpotifyClientCredentials(
#             client_id=config['spotify']['client_id'],
#             client_secret=config['spotify']['client_secret']
#         )
#         self.sp = spotipy.Spotify(auth_manager=auth_manager)


#     def _get_episode_id(self, url):
#         """SpotifyのURLからエピソードIDを抽出"""
#         try:
#             # URLからIDを抽出（最後の/以降の?より前の部分）
#             if '?' in url:
#                 episode_id = url.split('/')[-1].split('?')[0]
#             else:
#                 episode_id = url.split('/')[-1]
#             return episode_id
#         except Exception as e:
#             print(f"エピソードID抽出エラー: {str(e)}")
#             return None


#     # def get_episode_info(self, spotify_url):
#     #     # URLからエピソードIDを抽出
#     #     episode_id = re.search(r'episode/([a-zA-Z0-9]+)', spotify_url).group(1)
#     #     episode = self.sp.episode(episode_id)

#     #     return {
#     #         'title': episode['name'],
#     #         'description': episode['description'],
#     #         'duration_ms': episode['duration_ms'],
#     #         'release_date': episode['release_date']
#     #     }
#     def get_episode_info(self, url):
#         try:
#             episode_id = self._get_episode_id(url)
#             episode = self.spotify.episode(episode_id)

#             # ミリ秒を分:秒形式に変換
#             duration_ms = episode['duration_ms']
#             duration_min = duration_ms // (1000 * 60)
#             duration_sec = (duration_ms // 1000) % 60
#             duration = f"{duration_min}:{duration_sec:02d}"

#             # 公開日をフォーマット
#             release_date = datetime.strptime(episode['release_date'], '%Y-%m-%d').strftime('%Y年%m月%d日')

#             return {
#                 'title': episode['name'],
#                 'description': episode['description'],
#                 'release_date': release_date,
#                 'duration': duration
#             }
#         except Exception as e:
#             print(f"エピソード情報の取得に失敗: {str(e)}")
#             return None


# src/spotify.py
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from datetime import datetime
import yaml
import os


def load_config():
    """設定ファイルを読み込む"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
    with open(config_path, "r") as file:
        return yaml.safe_load(file)


class SpotifyClient:
    def __init__(self):
        self.config = load_config()
        auth_manager = SpotifyClientCredentials(
            client_id=self.config["spotify"]["client_id"],
            client_secret=self.config["spotify"]["client_secret"],
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def _get_episode_id(self, url):
        """SpotifyのURLからエピソードIDを抽出"""
        try:
            if "?" in url:
                episode_id = url.split("/")[-1].split("?")[0]
            else:
                episode_id = url.split("/")[-1]
            return episode_id
        except Exception as e:
            print(f"エピソードID抽出エラー: {str(e)}")
            return None

    # def get_episode_info(self, url):
    #     try:
    #         episode_id = self._get_episode_id(url)
    #         episode = self.sp.episode(episode_id)

    #         # ミリ秒を分:秒形式に変換
    #         duration_ms = episode['duration_ms']
    #         duration_min = duration_ms // (1000 * 60)
    #         duration_sec = (duration_ms // 1000) % 60
    #         duration = f"{duration_min}:{duration_sec:02d}"

    #         # 公開日をフォーマット
    #         release_date = datetime.strptime(episode['release_date'], '%Y-%m-%d').strftime('%Y年%m月%d日')

    #         return {
    #             'title': episode['name'],
    #             'description': episode['description'],
    #             'release_date': release_date,
    #             'duration': duration
    #         }
    #     except Exception as e:
    #         print(f"エピソード情報の取得に失敗: {str(e)}")
    #         return None

    def get_episode_info(self, url):
        """SpotifyのURLからエピソード情報を取得"""
        try:
            # URLからエピソードIDを抽出
            episode_id = url.split("/")[-1].split("?")[0]

            # エピソード情報を取得
            episode = self.sp.episode(episode_id)

            # 言語情報を取得（Spotifyは'en', 'ja'などのISO 639-1コードを使用）
            language = episode.get("language", "ja")

            # 番組名を取得
            show_name = episode.get("show", {}).get("name", "")

            # カバー画像URLを取得（エピソード固有の画像を優先、なければ番組画像）
            cover_image_url = ""

            # まずエピソード固有の画像を確認
            episode_images = episode.get("images", [])
            if episode_images:
                # 中程度のサイズ（300px前後）を優先、なければ最初の画像
                cover_image_url = episode_images[0]["url"]  # デフォルト
                for img in episode_images:
                    if img.get("height") and 200 <= img["height"] <= 400:
                        cover_image_url = img["url"]
                        break

            # エピソード固有の画像がない場合、番組画像を使用
            if not cover_image_url:
                show_images = episode.get("show", {}).get("images", [])
                if show_images:
                    # 中程度のサイズ（300px前後）を優先、なければ最初の画像
                    cover_image_url = show_images[0]["url"]  # デフォルト
                    for img in show_images:
                        if img.get("height") and 200 <= img["height"] <= 400:
                            cover_image_url = img["url"]
                            break

            return {
                "id": episode["id"],
                "title": episode["name"],
                "show_name": show_name,  # 番組名を追加
                "cover_image_url": cover_image_url,  # カバー画像URLを追加
                "description": episode["description"],
                "release_date": episode["release_date"],
                "duration_ms": episode["duration_ms"],
                "language": language,  # 言語情報を追加
            }

        except Exception as e:
            print(f"Spotify APIエラー: {str(e)}")
            raise

    def get_show_info(self, show_url):
        """SpotifyのShow URLから番組情報を取得"""
        try:
            # URLから番組IDを抽出
            show_id = show_url.split("/")[-1].split("?")[0]

            # 番組情報を取得
            show = self.sp.show(show_id)

            # カバー画像URLを取得（複数サイズから適切なサイズを選択）
            cover_image_url = ""
            show_images = show.get("images", [])
            if show_images:
                # 中程度のサイズ（300px前後）を優先、なければ最初の画像
                cover_image_url = show_images[0]["url"]  # デフォルト
                for img in show_images:
                    if img.get("height") and 200 <= img["height"] <= 400:
                        cover_image_url = img["url"]
                        break

            return {
                "id": show["id"],
                "name": show["name"],
                "description": show["description"],
                "cover_image_url": cover_image_url,
                "total_episodes": show["total_episodes"],
                "publisher": show.get("publisher", ""),
                "language": (
                    show.get("languages", ["ja"])[0] if show.get("languages") else "ja"
                ),
            }

        except Exception as e:
            print(f"Spotify Show APIエラー: {str(e)}")
            raise
