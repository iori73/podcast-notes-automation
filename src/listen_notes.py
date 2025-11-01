# src/listen_notes.py
import requests
from pathlib import Path
from utils import load_config
import urllib.parse
import os


class ListenNotesClient:
    def __init__(self):
        self.config = load_config()
        self.base_url = "https://listen-api.listennotes.com/api/v2"
        self.download_dir = Path('data/downloads')
        self.download_dir.mkdir(exist_ok=True)
        self.language = "Japanese"

    
    def search_episode(self, title):
        """タイトルからエピソードを検索"""
        search_params = {
            'q': title,
            'type': 'episode',
            'language': self.language,
            'safe_mode': 0,
            'sort_by_date': 0,  # 関連度順にソート
            'offset': 0,
            'len_min': 0,
            'len_max': 0
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/search",
                headers={'X-ListenAPI-Key': self.config['listen_notes']['api_key']},
                params=search_params
            )
            
            if response.status_code == 200:
                data = response.json()
                if not data.get('results'):
                    return None
                    
                # タイトルの完全一致を優先
                for episode in data['results']:
                    if episode['title_original'].strip() == title.strip():
                        return episode
                        
                # 完全一致がない場合は最も関連度の高い結果を返す
                return data['results'][0]
                
        except Exception as e:
            print(f"検索エラー: {str(e)}")
        return None



    def _calculate_title_similarity(self, title1, title2):
        """タイトルの類似度を計算"""
        # 簡単な文字列一致度計算（必要に応じて改善可能）
        title1 = title1.lower()
        title2 = title2.lower()
        
        # 完全一致の場合は最高スコア
        if title1 == title2:
            return 1.0
            
        # 部分一致のスコアを計算
        words1 = set(title1.split())
        words2 = set(title2.split())
        common_words = words1.intersection(words2)
        
        return len(common_words) / max(len(words1), len(words2))


    def get_episode_url(self, spotify_title):
        """SpotifyのタイトルからListen NotesのURLを取得"""
        episode = self.search_episode(spotify_title)
        if episode:
            # listennotes_urlを返す
            return episode.get('listennotes_url')
        return None





    def download_episode(self, episode_url, episode_title):
        """エピソードの音声をダウンロード"""
        try:
            # エピソードIDを抽出
            episode_id = episode_url.split('/')[-2]
            
            # APIを使用して音声URLを取得
            response = requests.get(
                f"{self.base_url}/episodes/{episode_id}",
                headers={'X-ListenAPI-Key': self.config['listen_notes']['api_key']}
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get episode: {response.status_code}")
                
            audio_url = response.json().get('audio')
            if not audio_url:
                raise Exception("No audio URL found")
            
            # ファイル名を作成して保存
            safe_title = episode_title.replace('/', '_').replace(':', '_')
            filename = self.download_dir / f"{safe_title}.mp3"
            
            # 音声ファイルをダウンロード
            audio_response = requests.get(audio_url, stream=True)
            if audio_response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in audio_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return filename
            
            raise Exception(f"Failed to download file: {audio_response.status_code}")
        except Exception as e:
            raise Exception(f"Download error: {str(e)}")



    

    def download_episode(self, episode_url, episode_title):
        """エピソードの音声をダウンロード"""
        try:
            # エピソードURLから音声URLを生成
            audio_url = episode_url.replace('www.', 'audio.').replace('/e/', '/e/p/')
            
            # ファイル名に使用できない文字を置換してタイトルを安全な形式に
            safe_title = episode_title.replace('/', '_').replace(':', '_')
            filename = self.download_dir / f"{safe_title}.mp3"
            
            # 音声ファイルをダウンロード
            response = requests.get(audio_url, stream=True)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return filename
            
            raise Exception(f"Failed to download file: {response.status_code}")
        except Exception as e:
            raise Exception(f"Download error: {str(e)}")


        

    def get_download_url(self, episode_url):
        """エピソードURLからダウンロードURLを取得"""
        # APIを使用してダウンロードURLを取得
        try:
            episode_id = episode_url.split('/')[-1]
            response = requests.get(
                f"{self.base_url}/episodes/{episode_id}",
                headers={'X-ListenAPI-Key': self.config['listen_notes']['api_key']}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('audio')
            else:
                print(f"ダウンロードURL取得エラー: {response.text}")
                
        except Exception as e:
            print(f"ダウンロードURL取得エラー: {str(e)}")
        
        return None
    
    def set_language(self, language):
        """
        language: "Japanese" or "English"
        """
        self.language = language
    
    
    