# src/listen_notes.py
import requests
from pathlib import Path
from utils import load_config
import urllib.parse
import os
import re
import struct


class ListenNotesClient:
    def __init__(self):
        self.config = load_config()
        self.base_url = "https://listen-api.listennotes.com/api/v2"
        self.download_dir = Path('data/downloads')
        self.download_dir.mkdir(exist_ok=True)
        self.language = "Japanese"

    def _normalize_podcast_name(self, name):
        """Normalize podcast name for comparison (remove spaces, punctuation, lowercase)"""
        if not name:
            return ""
        # Remove common variations and normalize
        name = name.lower()
        # Remove common prefixes/suffixes
        name = re.sub(r'\s*(podcast|ポッドキャスト|radio|ラジオ)\s*$', '', name, flags=re.IGNORECASE)
        # Remove punctuation and spaces
        name = re.sub(r'[^\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', '', name)
        return name

    def _podcast_names_match(self, expected_name, actual_name):
        """
        Check if podcast names match strictly.
        Returns True only if names are essentially the same podcast.
        """
        if not expected_name or not actual_name:
            return False
        
        norm_expected = self._normalize_podcast_name(expected_name)
        norm_actual = self._normalize_podcast_name(actual_name)
        
        # Exact match after normalization
        if norm_expected == norm_actual:
            return True
        
        # One contains the other (for cases like "Takram Cast" vs "Takram Cast Podcast")
        if norm_expected in norm_actual or norm_actual in norm_expected:
            # Make sure it's not a false positive (e.g., "Takram" should not match "TAKRAM RADIO")
            # Check if the shorter one is a significant portion of the longer one
            shorter = min(norm_expected, norm_actual, key=len)
            longer = max(norm_expected, norm_actual, key=len)
            # The shorter name should be at least 70% of the longer name
            if len(shorter) / len(longer) >= 0.7:
                return True
        
        return False
    
    def search_episode(self, title, show_name=None):
        """タイトルからエピソードを検索
        
        Args:
            title: エピソードのタイトル
            show_name: 番組名（オプション、指定すると番組名も一致するかチェック）
        """
        # まず完全なタイトルで検索
        search_queries = [title]
        
        # 番組名がある場合は、番組名とタイトルの組み合わせを優先
        if show_name:
            search_queries.insert(0, f"{show_name} {title}")
        
        # タイトルを分割して主要な部分を抽出
        # 「：」や「-」で分割された場合、最初の部分と主要なキーワードを使用
        parts = []
        if '：' in title:
            parts = title.split('：')
        elif '-' in title:
            parts = title.split('-')
        elif ' ' in title:
            parts = title.split(' ')
        
        if len(parts) > 1:
            if show_name:
                search_queries.append(f"{show_name} {parts[0].strip()}")
            search_queries.append(parts[0].strip())  # 最初の部分
            search_queries.append(parts[-1].strip())  # 最後の部分
            # 最初の2つの部分を組み合わせ
            if len(parts) >= 2:
                search_queries.append(f"{parts[0].strip()} {parts[1].strip()}")
        
        # 主要なキーワードを抽出（日本語文字のみ）
        keywords = re.findall(r'[\u4e00-\u9fff]+', title)
        if keywords:
            # 長いキーワードを優先（3文字以上）
            keywords = [kw for kw in keywords if len(kw) >= 3]
            keywords = sorted(keywords, key=len, reverse=True)
            if len(keywords) > 0:
                search_queries.append(keywords[0])  # 最長のキーワード
            if len(keywords) > 1:
                search_queries.append(' '.join(keywords[:2]))  # 上位2つのキーワード
            if len(keywords) > 2:
                search_queries.append(' '.join(keywords[:3]))  # 上位3つのキーワード
        
        for query in search_queries:
            search_params = {
                'q': query,
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
                        continue
                    
                    # 番組名が指定されている場合、STRICT MATCHING: 番組名が一致するエピソードのみを受け入れる
                    if show_name:
                        for episode in data['results']:
                            podcast_title = episode.get('podcast', {}).get('title_original', '')
                            episode_title = episode['title_original'].strip()
                            
                            # STRICT: Use normalized matching for podcast names
                            if not self._podcast_names_match(show_name, podcast_title):
                                continue  # Skip episodes from different podcasts
                            
                            # 番組名が一致し、タイトルも一致する場合
                            if episode_title == title.strip():
                                print(f"   ✅ 番組名・タイトル完全一致: {podcast_title} - {episode_title}")
                                return episode
                        
                        # 番組名が一致し、タイトルが部分一致する場合
                        for episode in data['results']:
                            podcast_title = episode.get('podcast', {}).get('title_original', '')
                            episode_title = episode['title_original'].strip()
                            
                            # STRICT: Use normalized matching for podcast names
                            if not self._podcast_names_match(show_name, podcast_title):
                                continue
                            
                            # タイトルの主要キーワードが含まれているか確認
                            title_parts = title.split('：') if '：' in title else [title]
                            if any(part.strip() in episode_title for part in title_parts if part.strip()):
                                print(f"   ✅ 番組名一致・タイトル部分一致: {podcast_title} - {episode_title}")
                                return episode
                        
                        # Log why we're skipping results
                        for episode in data['results'][:3]:  # Show first 3 results
                            podcast_title = episode.get('podcast', {}).get('title_original', '')
                            if not self._podcast_names_match(show_name, podcast_title):
                                print(f"   ❌ 番組名不一致でスキップ: 期待='{show_name}' 実際='{podcast_title}'")
                        continue  # 次の検索クエリを試す
                    
                    # 番組名が指定されていない場合のみ、タイトル一致をチェック
                    # （番組名がない場合は誤検出リスクが高いので慎重に）
                    for episode in data['results']:
                        if episode['title_original'].strip() == title.strip():
                            podcast_title = episode.get('podcast', {}).get('title_original', '')
                            print(f"   ⚠️ タイトル完全一致（番組名未指定）: {podcast_title}")
                            return episode
                    
                    # 番組名なしで部分一致は危険なので、スキップ
                    print(f"   ⚠️ 番組名が指定されていないため、部分一致をスキップします（誤検出防止）")
                    
            except Exception as e:
                print(f"検索エラー (クエリ: {query}): {str(e)}")
                continue
        
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


    def get_episode_url(self, spotify_title, show_name=None):
        """SpotifyのタイトルからListen NotesのURLを取得
        
        Args:
            spotify_title: エピソードのタイトル
            show_name: 番組名（オプション）
        """
        episode = self.search_episode(spotify_title, show_name=show_name)
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
    
    def verify_download(self, file_path, expected_duration_ms=None):
        """
        Verify that the downloaded file is a valid audio file.
        
        Args:
            file_path: Path to the downloaded file
            expected_duration_ms: Expected duration in milliseconds (optional)
        
        Returns:
            dict: {
                'valid': bool,
                'file_size': int,
                'is_mp3': bool,
                'duration_match': bool or None,
                'error': str or None
            }
        """
        result = {
            'valid': False,
            'file_size': 0,
            'is_mp3': False,
            'duration_match': None,
            'error': None
        }
        
        try:
            file_path = Path(file_path)
            
            # Check if file exists
            if not file_path.exists():
                result['error'] = 'File does not exist'
                return result
            
            # Check file size (minimum 1MB, maximum 500MB)
            file_size = file_path.stat().st_size
            result['file_size'] = file_size
            
            if file_size < 1 * 1024 * 1024:  # Less than 1MB
                result['error'] = f'File too small: {file_size / 1024 / 1024:.2f}MB (min 1MB)'
                return result
            
            if file_size > 500 * 1024 * 1024:  # More than 500MB
                result['error'] = f'File too large: {file_size / 1024 / 1024:.2f}MB (max 500MB)'
                return result
            
            # Check MP3 magic bytes
            with open(file_path, 'rb') as f:
                header = f.read(4)
                
                # MP3 magic bytes: ID3 tag or MPEG sync word
                is_mp3 = (
                    header[:3] == b'ID3' or  # ID3v2 tag
                    header[:2] == b'\xff\xfb' or  # MPEG Audio Layer 3
                    header[:2] == b'\xff\xfa' or  # MPEG Audio Layer 3
                    header[:2] == b'\xff\xf3' or  # MPEG Audio Layer 3
                    header[:2] == b'\xff\xf2'     # MPEG Audio Layer 3
                )
                
                result['is_mp3'] = is_mp3
                
                if not is_mp3:
                    # Check if it's HTML (common error response)
                    f.seek(0)
                    content_start = f.read(100).decode('utf-8', errors='ignore').lower()
                    if '<html' in content_start or '<!doctype' in content_start:
                        result['error'] = 'Downloaded file is HTML, not audio (likely 404 page)'
                        return result
                    result['error'] = 'File is not a valid MP3 file'
                    return result
            
            # Optional: Check duration if expected_duration_ms is provided
            if expected_duration_ms is not None:
                try:
                    # Estimate duration from file size (rough approximation)
                    # Average MP3 bitrate is ~128-192kbps
                    estimated_duration_s = file_size * 8 / (128 * 1024)  # Using 128kbps as baseline
                    expected_duration_s = expected_duration_ms / 1000
                    
                    # Allow 50% tolerance (MP3 bitrates vary)
                    tolerance = 0.5
                    if abs(estimated_duration_s - expected_duration_s) / expected_duration_s <= tolerance:
                        result['duration_match'] = True
                    else:
                        result['duration_match'] = False
                        print(f"   ⚠️ Duration mismatch: estimated {estimated_duration_s/60:.1f}min vs expected {expected_duration_s/60:.1f}min")
                except:
                    result['duration_match'] = None
            
            result['valid'] = True
            return result
            
        except Exception as e:
            result['error'] = str(e)
            return result
    
    