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
            # ⚠️ 注意: この値は配信者が手動で設定するメタデータで、誤登録されることがある
            # （例: ep #382 は日本語音声なのに "en" タグだった）。呼び出し側はこの値を
            # Whisperの language 引数にそのまま渡さないこと（Whisperはこれを強制指定として扱い、
            # 違う言語の音声を無理に当てはめて読み取り不能な出力になる）。
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
            # Fallback: the Web API rejects episode/show reads with a 403
            # ("Active premium subscription required for the owner of the app")
            # whenever the app owner's Spotify account is not on an active
            # Premium plan. That block is server-side and unrelated to our
            # credentials, so scrape the public episode page's OpenGraph tags
            # to recover enough metadata to keep the pipeline running.
            fallback = self._scrape_episode_og(url)
            if fallback:
                print("↩️  Recovered metadata from public page (OpenGraph fallback)")
                return fallback
            raise

    def _scrape_episode_og(self, url):
        """Recover episode metadata from the public open.spotify.com page.

        Used when the Web API is unavailable (e.g. the app-owner-premium 403).
        Returns the same dict shape as get_episode_info, or None on failure.
        """
        import re as _re
        import requests as _requests

        try:
            episode_id = url.split("/")[-1].split("?")[0]
            # Spotify serves the OpenGraph-rich page only to crawler-style
            # User-Agents; a full browser UA gets the JS web-player shell that
            # has no og:title/og:image. Use a known crawler UA.
            headers = {"User-Agent": "facebookexternalhit/1.1"}
            resp = _requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text

            def _meta(prop):
                m = _re.search(
                    r'<meta[^>]+(?:property|name)=["\']' + _re.escape(prop)
                    + r'["\'][^>]+content=["\']([^"\']*)["\']',
                    html,
                )
                return m.group(1) if m else ""

            title = _meta("og:title")
            if not title:
                return None

            # og:description is "<show name> · Episode" for episodes.
            raw_desc = _meta("og:description")
            show_name = _re.sub(r"\s*·\s*Episode\s*$", "", raw_desc).strip()

            duration_s = _meta("music:duration")
            duration_ms = int(duration_s) * 1000 if duration_s.isdigit() else 0

            return {
                "id": episode_id,
                "title": title,
                "show_name": show_name,
                "cover_image_url": _meta("og:image"),
                "description": raw_desc,
                "release_date": "",  # not exposed via OpenGraph
                "duration_ms": duration_ms,
                "language": "ja",  # OG has no language; caller may override
            }
        except Exception as scrape_err:
            print(f"OpenGraph fallback failed: {scrape_err}")
            return None

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
