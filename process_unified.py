#!/usr/bin/env python3
"""
Unified Podcast Processing Script

This script implements the recommended workflow:
1. Listen Notes Search -> Download Audio -> Whisper Transcription
2. Fallback: Browser MCP -> Spotify HTML Extraction (Claude-driven)
3. Claude: Chapter Titles + Summary Generation
4. Notion Upload with Cover Image

Usage:
    python process_unified.py <spotify_url> [options]

Examples:
    # Basic usage - Listen Notes search + Whisper
    python process_unified.py "https://open.spotify.com/episode/xxx"
    
    # With language override
    python process_unified.py "https://open.spotify.com/episode/xxx" --language ja
    
    # Process from local HTML (Spotify "Listen Along" export)
    python process_unified.py "https://open.spotify.com/episode/xxx" --html-file transcript.html
    
    # Process from local audio file (skip Listen Notes)
    python process_unified.py "https://open.spotify.com/episode/xxx" --audio-file episode.mp3
    
    # Skip Notion upload
    python process_unified.py "https://open.spotify.com/episode/xxx" --no-notion
"""

import argparse
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional

# Add src directories to path
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/integrations')
sys.path.insert(0, 'local_transcriber')

from spotify import SpotifyClient
from listen_notes import ListenNotesClient
from notion_client import NotionClient
from integrations.itunes_rss import iTunesRSSClient
from utils import load_config


class UnifiedProcessor:
    """Unified podcast processing with multiple fallback options."""
    
    def __init__(self):
        self.spotify_client = SpotifyClient()
        self.listen_notes_client = ListenNotesClient()
        self.notion_client = NotionClient()
        self.itunes_client = iTunesRSSClient()
        self._init_gemini()
        
        self.episode_info = None
        self.transcript = None
        self.timestamps_raw = []
        self.summary = None
        self.key_takeaways = None
        self.chapters = None
        self.category = None
        self.source = None  # 'whisper', 'spotify_html', 'itunes_rss', or 'manual'

    def _init_gemini(self):
        """Initialize Gemini client if configured."""
        self.gemini_client = None
        self.gemini_model_name = None
        try:
            config = load_config()
            api_key = (config.get("gemini") or {}).get("api_key")
            if not api_key:
                return

            from google import genai

            client = genai.Client(api_key=api_key)
            for name in ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-flash-lite", "gemini-2.0-flash"]:
                try:
                    client.models.generate_content(model=name, contents="ping")
                    self.gemini_client = client
                    self.gemini_model_name = name
                    break
                except Exception:
                    continue
        except Exception:
            self.gemini_client = None
            self.gemini_model_name = None

    def _gemini_generate(self, prompt: str) -> Optional[str]:
        """Generate text via Gemini if available."""
        if not self.gemini_client or not self.gemini_model_name:
            return None
        try:
            resp = self.gemini_client.models.generate_content(
                model=self.gemini_model_name, contents=prompt
            )
            text = getattr(resp, "text", None)
            return text.strip() if text else None
        except Exception as e:
            print(f"⚠️ Gemini error: {e}")
            return None

    def _split_text(self, text: str, max_chars: int) -> List[str]:
        """Split long text into chunks, trying to respect sentence boundaries."""
        if len(text) <= max_chars:
            return [text]
        chunks = []
        buf = ""
        for part in re.split(r"(\n+|。|！|？)", text):
            if not part:
                continue
            if len(buf) + len(part) <= max_chars:
                buf += part
                continue
            if buf.strip():
                chunks.append(buf.strip())
            buf = part
        if buf.strip():
            chunks.append(buf.strip())
        return chunks

    def _to_seconds(self, ts: str) -> int:
        """Convert M:SS or MM:SS to seconds."""
        try:
            mm, ss = ts.split(":")
            return int(mm) * 60 + int(ss)
        except Exception:
            return 0

    def _format_mmss(self, seconds: int) -> str:
        mm = seconds // 60
        ss = seconds % 60
        return f"{mm:02d}:{ss:02d}"

    def _build_chapter_context(self, interval_sec: int = 300, max_items: int = 14) -> List[Tuple[str, str]]:
        """
        Build chapter context lines from timestamps_raw by bucketing into intervals.
        Returns list of (MM:SS, snippet).
        """
        if not self.timestamps_raw:
            return []

        buckets = {}
        for ts, text in self.timestamps_raw:
            sec = self._to_seconds(ts)
            bucket = (sec // interval_sec) * interval_sec
            if bucket not in buckets:
                buckets[bucket] = []
            if text:
                buckets[bucket].append(text.strip())

        items = []
        for bucket in sorted(buckets.keys()):
            combined = " ".join(buckets[bucket])
            combined = re.sub(r"\s+", " ", combined).strip()
            if len(combined) > 220:
                combined = combined[:217] + "..."
            items.append((self._format_mmss(bucket), combined))

        # Ensure 00:00 exists
        if items and items[0][0] != "00:00":
            items.insert(0, ("00:00", items[0][1]))

        if len(items) <= max_items:
            return items

        # For long episodes, pick evenly across the timeline
        step = max(1, len(items) // max_items)
        picked = items[::step][:max_items]
        if picked[-1] != items[-1] and len(picked) < max_items:
            picked.append(items[-1])
        return picked[:max_items]

    def _generate_summary_and_timestamps(self, language: str):
        """Generate summary and timestamps (chapter titles) from transcript via Gemini."""
        if not self.gemini_client:
            self.chapters = self._generate_chapter_placeholders()
            self.summary = self._generate_summary_placeholder()
            return

        lang = "日本語" if language == "ja" else "English"
        title = (self.episode_info or {}).get("title", "")
        show = (self.episode_info or {}).get("show_name", "")

        # --- Summary (map-reduce style) ---
        chunks = self._split_text(self.transcript or "", max_chars=8000)
        if len(chunks) > 6:
            mid = len(chunks) // 2
            chunks = chunks[:2] + chunks[mid:mid+2] + chunks[-2:]

        chunk_summaries = []
        for idx, chunk in enumerate(chunks, start=1):
            prompt = f"""
あなたは優秀な編集者です。次のポッドキャスト文字起こし（断片）を{lang}で要点整理してください。

条件:
- 断片の要点を箇条書きで5個まで
- 固有名詞/キーワードがあれば含める
- 余計な前置きや自己言及は禁止

番組: {show}
回: {title}

文字起こし（断片 {idx}/{len(chunks)}）:
{chunk}

出力:
- ...
""".strip()
            out = self._gemini_generate(prompt)
            if out:
                chunk_summaries.append(out)

        final_prompt = f"""
あなたは優秀な編集者です。以下はポッドキャストの要点メモ（複数断片のまとめ）です。
これを元に、{lang}で「Summary」と「Key Takeaways」を作成してください。

【Summaryの条件】
- 250〜450文字程度（英語の場合は600〜900 characters程度）
- エピソードで実際に議論・紹介された内容を具体的に要約する
- タイトルをそのまま言い換えるだけの要約は禁止
- 番組の定型紹介文（「〜という番組です」など）を含めるのは禁止
- ゲスト紹介だけで終わる要約は禁止
- 「このエピソードでは〜について話されています」という書き方は禁止
- 具体的に何が語られたか、どんな主張・知見・事例・データが紹介されたかを書く
- 内容の推測はせず、与えられた情報の範囲で

【Key Takeawaysの条件】
- 箇条書きで3〜5点
- このエピソード固有の学び・気づき・主張を書く
- 「〜について学べます」などの抽象的な表現は禁止
- 具体的な数字・事例・人名・概念名を含める

番組: {show}
回: {title}

要点メモ:
{chr(10).join(chunk_summaries) if chunk_summaries else (self.transcript or "")[:12000]}

出力形式（この順番で、見出し行も含めて出力）:
Summary:
...

Key Takeaways:
- ...
""".strip()
        final = self._gemini_generate(final_prompt)
        if final:
            # SummaryとKey Takeawaysを分割
            parts = re.split(r'Key Takeaways:\s*\n', final, maxsplit=1)
            if len(parts) == 2:
                summary_part = parts[0].strip()
                # "Summary:" ヘッダーを除去
                summary_part = re.sub(r'^Summary:\s*\n?', '', summary_part).strip()
                self.summary = summary_part
                self.key_takeaways = parts[1].strip()
            else:
                # フォールバック: 分割できなかった場合は全体をsummaryに
                self.summary = final.strip()
                self.key_takeaways = None
        else:
            self.summary = self._generate_summary_placeholder()
            self.key_takeaways = None

        # --- Timestamps / Chapters ---
        chapter_items = self._build_chapter_context(interval_sec=300, max_items=14)
        if not chapter_items:
            self.chapters = self._generate_chapter_placeholders()
            return

        chapter_context = "\n".join([f"{ts} {snippet}" for ts, snippet in chapter_items if snippet])
        chapter_prompt = f"""
あなたはポッドキャストの編集者です。以下の時刻ごとの内容メモから、章タイトル（チャプター目次）を作ってください。

条件:
- 各行の時刻（MM:SS）はそのまま維持（変更しない）
- 時刻の後に、内容を表す短いタイトルを付ける（{lang}で 15〜30文字程度）
- 出力は「MM:SS タイトル」のみ（余計な説明は禁止）

番組: {show}
回: {title}

内容メモ:
{chapter_context}

出力:
""".strip()
        chapters = self._gemini_generate(chapter_prompt)
        self.chapters = chapters.strip() if chapters else self._generate_chapter_placeholders()

    VALID_CATEGORIES = [
        "Technology", "Biology & Nature", "Science", "Design & Art",
        "Startup & VC", "Education", "Career", "AI", "Others", "Business"
    ]

    def _classify_category(self, language: str) -> str:
        """Classify episode into a category using Gemini."""
        if not self.gemini_client:
            return "Others"

        title = (self.episode_info or {}).get("title", "")
        show = (self.episode_info or {}).get("show_name", "")
        transcript_head = (self.transcript or "")[:300]

        prompt = f"""Classify this podcast episode into exactly one category.
Return ONLY the category name, nothing else.

Categories: {', '.join(self.VALID_CATEGORIES)}

Title: {title}
Podcast: {show}
Content: {transcript_head}"""

        result = self._gemini_generate(prompt)
        if result:
            category = result.strip().strip('"').strip("'")
            if category in self.VALID_CATEGORIES:
                return category
            # 部分一致で探す
            for valid in self.VALID_CATEGORIES:
                if valid.lower() in category.lower():
                    return valid
        return "Others"

    def process(
        self,
        spotify_url: str,
        language: str = None,
        html_file: str = None,
        audio_file: str = None,
        no_notion: bool = False,
        whisper_model: str = "medium"
    ) -> dict:
        """
        Main processing entry point.
        
        Returns:
            dict: Processing result with status and data
        """
        print("=" * 60)
        print("🎙️ UNIFIED PODCAST PROCESSOR")
        print("=" * 60)
        print(f"📌 Spotify URL: {spotify_url}")
        print("=" * 60)
        
        # Step 1: Fetch Spotify Metadata
        print("\n📡 STEP 1: Fetching Spotify Metadata...")
        self.episode_info = self._fetch_spotify_metadata(spotify_url)
        
        if not self.episode_info:
            return {"success": False, "error": "Failed to fetch Spotify metadata"}
        
        self._print_episode_info()
        
        # Determine language (from Spotify or override)
        detected_language = self.episode_info.get('language', 'ja')
        effective_language = language or detected_language
        print(f"\n🌐 Language: {effective_language}")
        
        # Step 2: Get Transcript (multiple methods)
        print("\n" + "=" * 60)
        print("STEP 2: Obtaining Transcript")
        print("=" * 60)
        
        transcript_result = None
        
        # Method A: From provided HTML file
        if html_file:
            print(f"\n📄 Using provided HTML file: {html_file}")
            transcript_result = self._extract_from_html(html_file)
            self.source = 'spotify_html'
        
        # Method B: From provided audio file
        elif audio_file:
            print(f"\n🎵 Using provided audio file: {audio_file}")
            transcript_result = self._transcribe_with_whisper(audio_file, effective_language, whisper_model)
            self.source = 'whisper'
        
        # Method C: Listen Notes search -> Download -> Whisper
        else:
            print("\n🔍 Searching Listen Notes...")
            transcript_result = self._process_via_listen_notes(effective_language, whisper_model)
            
            # Fallback: Guide user for Browser MCP
            if not transcript_result:
                print("\n" + "=" * 60)
                print("⚠️ ALL AUTOMATIC METHODS FAILED")
                print("=" * 60)
                print("\n❌ Listen Notes: エピソードが見つかりません")
                print("❌ iTunes/RSS: Apple Podcastに登録されていないか、エピソードが見つかりません")
                print("\n次のステップを試してください:")
                print("\n【オプション1】Browser MCPでSpotify HTMLを取得")
                print("  1. Browser MCPでSpotify URLを開く")
                print("  2. 「聴きながら読む」をクリック")
                print("  3. HTMLをファイルに保存")
                print("  4. このスクリプトを --html-file オプションで再実行")
                print(f"\n  コマンド例:")
                print(f"  python process_unified.py \"{spotify_url}\" --html-file transcript.html")
                print("\n【オプション2】手動で音声ファイルをダウンロード")
                print(f"  python process_unified.py \"{spotify_url}\" --audio-file episode.mp3")
                
                return {
                    "success": False,
                    "error": "All automatic search methods failed (Listen Notes + iTunes/RSS)",
                    "fallback_required": True,
                    "episode_info": self.episode_info
                }
        
        if not transcript_result:
            return {"success": False, "error": "Failed to obtain transcript"}
        
        self.transcript = transcript_result.get('transcript', '')
        self.timestamps_raw = transcript_result.get('timestamps_raw', [])
        
        print(f"\n✅ Transcript obtained!")
        print(f"   Source: {self.source}")
        print(f"   Characters: {len(self.transcript)}")
        print(f"   Timestamps: {len(self.timestamps_raw)} sections")
        
        # Step 3: Generate Chapters and Summary (placeholder for Claude)
        print("\n" + "=" * 60)
        print("STEP 3: Chapter & Summary Generation")
        print("=" * 60)
        print("\n🧠 Generating summary & timestamps...")
        self._generate_summary_and_timestamps(effective_language)

        print("\n🏷️ Classifying category...")
        self.category = self._classify_category(effective_language)
        print(f"   Category: {self.category}")

        # Step 4: Save Output
        print("\n" + "=" * 60)
        print("STEP 4: Saving Output")
        print("=" * 60)
        
        output_path = self._save_output(spotify_url)
        print(f"✅ Saved to: {output_path}")
        
        # Step 5: Upload to Notion
        if not no_notion:
            print("\n" + "=" * 60)
            print("STEP 5: Uploading to Notion")
            print("=" * 60)
            
            notion_result = self._upload_to_notion(spotify_url, output_path)
            if notion_result:
                print("✅ Notion upload complete!")
            else:
                print("⚠️ Notion upload failed")
        else:
            print("\n⏩ Skipping Notion upload")
        
        print("\n" + "=" * 60)
        print("✅ PROCESSING COMPLETE")
        print("=" * 60)
        print(f"📂 Output: {output_path}")
        print(f"📊 Source: {self.source}")
        print(f"📝 Characters: {len(self.transcript)}")
        
        return {
            "success": True,
            "output_path": str(output_path),
            "source": self.source,
            "episode_info": self.episode_info,
            "transcript_length": len(self.transcript)
        }
    
    def _fetch_spotify_metadata(self, spotify_url: str) -> dict:
        """Fetch episode metadata from Spotify."""
        try:
            return self.spotify_client.get_episode_info(spotify_url)
        except Exception as e:
            print(f"❌ Spotify API error: {e}")
            return None
    
    def _print_episode_info(self):
        """Print episode information."""
        info = self.episode_info
        print(f"   ✅ Title: {info.get('title', 'N/A')}")
        print(f"   ✅ Podcast: {info.get('show_name', 'N/A')}")
        print(f"   ✅ Release Date: {info.get('release_date', 'N/A')}")
        
        duration_ms = info.get('duration_ms', 0)
        if duration_ms:
            minutes = duration_ms // (1000 * 60)
            seconds = (duration_ms // 1000) % 60
            print(f"   ✅ Duration: {minutes}:{seconds:02d}")
        
        cover_url = info.get('cover_image_url', '')
        if cover_url:
            print(f"   ✅ Cover: {cover_url[:50]}...")
    
    def _process_via_listen_notes(self, language: str, whisper_model: str) -> dict:
        """Try to find and process via Listen Notes, with iTunes/RSS fallback."""
        title = self.episode_info.get('title', '')
        show_name = self.episode_info.get('show_name', '')
        release_date = self.episode_info.get('release_date', '')
        duration_ms = self.episode_info.get('duration_ms')
        
        # Set language for Listen Notes search
        ln_language = "Japanese" if language in ['ja', 'Japanese'] else "English"
        self.listen_notes_client.set_language(ln_language)
        
        # Search for episode
        print(f"\n🔍 Searching: {show_name} - {title}")
        ln_url = self.listen_notes_client.get_episode_url(title, show_name)
        
        if not ln_url:
            print("❌ Episode not found on Listen Notes")
            
            # Try searching local downloads first
            local_file = self._find_local_audio()
            if local_file:
                print(f"✅ Found local file: {local_file}")
                return self._transcribe_with_whisper(str(local_file), language, whisper_model)
            
            # === iTunes/RSS Fallback ===
            print("\n" + "-" * 50)
            print("🔄 Trying iTunes/RSS fallback...")
            print("-" * 50)
            
            itunes_result = self._process_via_itunes_rss(language, whisper_model)
            if itunes_result:
                return itunes_result
            
            return None
        
        print(f"✅ Found: {ln_url}")
        
        # Download audio
        print("\n📥 Downloading audio...")
        try:
            downloaded_file = self.listen_notes_client.download_episode(ln_url, title)
            
            # Verify download
            verification = self.listen_notes_client.verify_download(
                downloaded_file,
                self.episode_info.get('duration_ms')
            )
            
            if not verification.get('valid'):
                print(f"❌ Download verification failed: {verification.get('error')}")
                # Listen Notesのファイルが無効な場合も iTunes/RSS フォールバックを試す
                print("\n" + "-" * 50)
                print("🔄 Trying iTunes/RSS fallback...")
                print("-" * 50)
                itunes_result = self._process_via_itunes_rss(language, whisper_model)
                if itunes_result:
                    return itunes_result
                return None
            
            print(f"✅ Downloaded: {downloaded_file}")
            print(f"   Size: {verification['file_size'] / (1024*1024):.1f}MB")
            
            # Transcribe with Whisper
            return self._transcribe_with_whisper(str(downloaded_file), language, whisper_model)
            
        except Exception as e:
            print(f"❌ Download error: {e}")
            print("\n" + "-" * 50)
            print("🔄 Trying iTunes/RSS fallback...")
            print("-" * 50)
            itunes_result = self._process_via_itunes_rss(language, whisper_model)
            if itunes_result:
                return itunes_result
            return None
    
    def _process_via_itunes_rss(self, language: str, whisper_model: str) -> dict:
        """
        Fallback: Try to find and process via iTunes Search API and RSS feed.
        
        This method:
        1. Searches for the podcast on Apple Podcasts via iTunes API
        2. Gets the RSS feed URL
        3. Parses the RSS to find the episode audio URL
        4. Downloads and transcribes the audio
        """
        title = self.episode_info.get('title', '')
        show_name = self.episode_info.get('show_name', '')
        release_date = self.episode_info.get('release_date', '')
        duration_ms = self.episode_info.get('duration_ms')
        
        try:
            # Search iTunes and get audio URL
            result = self.itunes_client.get_episode_audio(
                show_name=show_name,
                episode_title=title,
                release_date=release_date,
                duration_ms=duration_ms
            )
            
            if not result:
                print("❌ iTunes/RSS search failed")
                return None
            
            audio_url = result.get('audio_url')
            if not audio_url:
                print("❌ No audio URL found in RSS")
                return None
            
            # Download audio
            safe_title = title.replace('/', '／').replace(':', '：').replace('?', '？')
            safe_title = safe_title[:100]  # Limit filename length
            
            downloads_dir = Path('data/downloads')
            downloads_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = downloads_dir / f"{safe_title}.mp3"
            
            if self.itunes_client.download_audio(audio_url, str(output_path)):
                print(f"\n✅ Audio downloaded via iTunes/RSS")
                self.source = 'itunes_rss'
                return self._transcribe_with_whisper(str(output_path), language, whisper_model)
            else:
                print("❌ Audio download failed")
                return None
                
        except Exception as e:
            print(f"❌ iTunes/RSS processing error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_local_audio(self) -> Path:
        """Search for matching audio file in local downloads."""
        downloads_dir = Path('data/downloads')
        if not downloads_dir.exists():
            return None
        
        title = self.episode_info.get('title', '')
        show_name = self.episode_info.get('show_name', '')
        
        # Extract keywords
        keywords = re.findall(r'[\u4e00-\u9fff]+', title)  # Japanese characters
        keywords.extend(re.findall(r'[a-zA-Z]+', title))    # English words
        keywords = [kw for kw in keywords if len(kw) >= 2]
        
        best_match = None
        best_score = 0
        
        for mp3_file in downloads_dir.glob('*.mp3'):
            file_name = mp3_file.name.lower()
            score = 0
            
            # Direct title match
            if title.lower() in file_name or file_name in title.lower():
                score += 10
            
            # Keyword matching
            for kw in keywords:
                if kw.lower() in file_name:
                    score += len(kw)
            
            # Show name matching
            if show_name and show_name.lower() in file_name:
                score += 5
            
            if score > best_score:
                best_score = score
                best_match = mp3_file
        
        if best_score >= 3:  # Minimum threshold
            return best_match
        
        return None
    
    def _transcribe_with_whisper(self, audio_path: str, language: str, model_size: str) -> dict:
        """Transcribe audio using local Whisper."""
        print(f"\n🎙️ Transcribing with Whisper (model: {model_size})...")
        
        try:
            from transcriber import WhisperTranscriber
            
            transcriber = WhisperTranscriber(model_size=model_size)
            result = transcriber.transcribe(audio_path, language=language)
            
            self.source = 'whisper'
            
            # Convert segments to timestamps_raw format
            timestamps_raw = []
            for segment in result.get('segments', []):
                start_sec = int(segment['start'])
                minutes = start_sec // 60
                seconds = start_sec % 60
                timestamp = f"{minutes}:{seconds:02d}"
                text = segment['text'].strip()
                timestamps_raw.append((timestamp, text))
            
            return {
                'transcript': result['transcription'],
                'timestamps_raw': timestamps_raw,
                'language': result['language']
            }
            
        except ImportError:
            print("❌ Whisper not available. Install with: pip install openai-whisper")
            return None
        except Exception as e:
            print(f"❌ Whisper error: {e}")
            return None
    
    def _extract_from_html(self, html_path: str) -> dict:
        """Extract transcript from Spotify HTML."""
        from bs4 import BeautifulSoup
        
        html_path = Path(html_path)
        if not html_path.exists():
            print(f"❌ HTML file not found: {html_path}")
            return None
        
        print(f"📄 Extracting from: {html_path}")
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract timestamps and text
        transcript_parts = []
        current_timestamp = None
        
        for element in soup.find_all(['button', 'p']):
            if element.name == 'button':
                span = element.find('span')
                if span:
                    timestamp = span.get_text().strip()
                    if re.match(r'\d+:\d+', timestamp):
                        current_timestamp = timestamp
            elif element.name == 'p':
                text = self._clean_text(element.get_text())
                if text and current_timestamp:
                    transcript_parts.append((current_timestamp, text))
        
        # Group by timestamp
        grouped = {}
        for ts, text in transcript_parts:
            if ts not in grouped:
                grouped[ts] = []
            grouped[ts].append(text)
        
        # Build timestamps_raw and full transcript
        timestamps_raw = []
        full_transcript = []
        
        for ts in sorted(grouped.keys(), key=lambda x: tuple(map(int, x.split(':')))):
            combined_text = ' '.join(grouped[ts])
            timestamps_raw.append((ts, combined_text))
            full_transcript.append(combined_text)
        
        self.source = 'spotify_html'
        
        return {
            'transcript': '\n\n'.join(full_transcript),
            'timestamps_raw': timestamps_raw
        }
    
    def _clean_text(self, text: str) -> str:
        """Clean text from HTML extraction."""
        # Replace newlines with spaces
        text = text.replace('\n', ' ')
        # Multiple spaces to single
        text = re.sub(r'\s+', ' ', text)
        # Remove spaces between Japanese characters
        text = re.sub(
            r'(?<=[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]) (?=[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])',
            '', text
        )
        # Remove spaces around punctuation
        text = re.sub(r'\s*([。、！？])\s*', r'\1', text)
        return text.strip()
    
    def _generate_chapter_placeholders(self) -> str:
        """Generate chapter placeholders from timestamps."""
        if not self.timestamps_raw:
            return "チャプター情報なし"
        
        # Select key timestamps (every ~3 minutes)
        key_chapters = []
        last_minute = -3
        
        for ts, text in self.timestamps_raw:
            parts = ts.split(':')
            minutes = int(parts[0])
            
            if minutes >= last_minute + 3:
                # Get first sentence as placeholder
                first_sentence = text.split('。')[0] if '。' in text else text[:50]
                if len(first_sentence) > 50:
                    first_sentence = first_sentence[:47] + '...'
                key_chapters.append(f"{ts} {first_sentence}")
                last_minute = minutes
        
        return '\n'.join(key_chapters) if key_chapters else "チャプター情報なし"
    
    def _generate_summary_placeholder(self) -> str:
        """Generate a summary placeholder."""
        if not self.transcript:
            return "要約情報なし"
        
        # Use first few sentences as placeholder
        sentences = self.transcript.split('。')[:5]
        summary = '。'.join(s for s in sentences if s.strip())
        if summary and not summary.endswith('。'):
            summary += '。'
        
        if len(summary) > 400:
            summary = summary[:397] + '...'
        
        return summary
    
    def _format_duration(self, duration_ms: int) -> str:
        """Format duration from milliseconds."""
        if not duration_ms:
            return "N/A"
        
        total_seconds = duration_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
    
    def _break_long_line(self, text: str, max_len: int = 120) -> str:
        """長い1行を max_len 付近で区切り文字（、。スペース等）の直後に改行する。"""
        if len(text) <= max_len:
            return text
        lines = []
        rest = text
        while rest:
            rest = rest.lstrip()
            if not rest:
                break
            if len(rest) <= max_len:
                lines.append(rest)
                break
            chunk = rest[: max_len + 1]
            break_at = -1
            for sep in (" ", "、", "。", ".", "」", "）", ")"):
                pos = chunk.rfind(sep)
                if pos > max_len // 2:
                    break_at = pos + 1
                    break
            if break_at <= 0:
                break_at = max_len
            lines.append(rest[:break_at].strip())
            rest = rest[break_at:]
        return "\n\n".join(lines)

    def _format_transcript_with_newlines(self, text: str) -> str:
        """トランスクリプトを文の区切り（。！？ . ! ?）で改行し、長い塊は約120文字で折り返して読みやすくする。"""
        if not text or not text.strip():
            return text
        t = text.strip()
        # 文末記号の直後に改行を挿入（日本語＋英語）
        t = re.sub(r'([。！？.!?])', r'\1\n\n', t).strip()
        # 改行で区切られた各段落について、長すぎる場合は適切な位置でさらに改行
        parts = [p.strip() for p in t.split("\n\n") if p.strip()]
        formatted = []
        for part in parts:
            formatted.append(self._break_long_line(part, 120))
        return "\n\n".join(formatted)
    
    def _save_output(self, spotify_url: str) -> Path:
        """Save the processed content to markdown file."""
        title = self.episode_info.get('title', 'Unknown')
        safe_title = title.replace('/', '／').replace(':', '：').replace('?', '？')
        
        output_dir = Path('data/outputs') / safe_title
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / 'episode_summary.md'
        
        duration_str = self._format_duration(self.episode_info.get('duration_ms'))
        transcript_formatted = self._format_transcript_with_newlines(self.transcript or "")
        
        key_takeaways_section = ""
        if self.key_takeaways:
            key_takeaways_section = f"""## Key Takeaways

{self.key_takeaways}

"""
        content = f"""## Summary

{self.summary}

{key_takeaways_section}## Timestamps

{self.chapters}

## Transcript

{transcript_formatted}
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_path
    
    def _upload_to_notion(self, spotify_url: str, output_path: Path) -> bool:
        """Upload to Notion database."""
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            duration_ms = self.episode_info.get('duration_ms', 0)
            duration_minutes = duration_ms / (1000 * 60) if duration_ms else None
            
            page_id = self.notion_client.create_page(
                title=self.episode_info.get('title', 'Unknown'),
                markdown_content=markdown_content,
                spotify_url=spotify_url,
                cover_url=self.episode_info.get('cover_image_url'),
                podcast_name=self.episode_info.get('show_name'),
                release_date=self.episode_info.get('release_date'),
                duration_minutes=duration_minutes,
                category=self.category
            )
            
            return page_id is not None
            
        except Exception as e:
            print(f"❌ Notion upload error: {e}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Unified Podcast Processor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic: Listen Notes search + Whisper transcription
    python process_unified.py "https://open.spotify.com/episode/xxx"
    
    # From Spotify HTML (when Listen Notes fails)
    python process_unified.py "https://open.spotify.com/episode/xxx" --html-file transcript.html
    
    # From local audio file
    python process_unified.py "https://open.spotify.com/episode/xxx" --audio-file episode.mp3
    
    # Skip Notion upload
    python process_unified.py "https://open.spotify.com/episode/xxx" --no-notion
        """
    )
    
    parser.add_argument('spotify_url', type=str, help='Spotify episode URL')
    parser.add_argument('--language', '-l', type=str, choices=['ja', 'en'], help='Override language detection')
    parser.add_argument('--html-file', type=str, help='Spotify HTML transcript file (fallback)')
    parser.add_argument('--audio-file', type=str, help='Local audio file (skip Listen Notes)')
    parser.add_argument('--whisper-model', type=str, default='medium', choices=['tiny', 'base', 'small', 'medium', 'large'], help='Whisper model size')
    parser.add_argument('--no-notion', action='store_true', help='Skip Notion upload')
    
    args = parser.parse_args()
    
    processor = UnifiedProcessor()
    result = processor.process(
        spotify_url=args.spotify_url,
        language=args.language,
        html_file=args.html_file,
        audio_file=args.audio_file,
        no_notion=args.no_notion,
        whisper_model=args.whisper_model
    )
    
    if result.get('success'):
        sys.exit(0)
    else:
        if result.get('fallback_required'):
            print("\n💡 フォールバック処理が必要です。上記の指示に従ってください。")
        sys.exit(1)


if __name__ == "__main__":
    main()



