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

# Add src directories to path
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/integrations')
sys.path.insert(0, 'local_transcriber')

from spotify import SpotifyClient
from listen_notes import ListenNotesClient
from notion_client import NotionClient


class UnifiedProcessor:
    """Unified podcast processing with multiple fallback options."""
    
    def __init__(self):
        self.spotify_client = SpotifyClient()
        self.listen_notes_client = ListenNotesClient()
        self.notion_client = NotionClient()
        
        self.episode_info = None
        self.transcript = None
        self.timestamps_raw = []
        self.summary = None
        self.chapters = None
        self.source = None  # 'whisper', 'spotify_html', or 'manual'
    
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
                print("⚠️ LISTEN NOTES SEARCH FAILED")
                print("=" * 60)
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
                    "error": "Listen Notes search failed",
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
        print("\n⚠️ この処理はClaudeが対話的に実行します")
        print("   - チャプター目次: Claudeが文字起こしから適切なタイトルを生成")
        print("   - 要約: Claudeが内容を要約")
        
        # Create placeholder chapters (Claude will refine)
        self.chapters = self._generate_chapter_placeholders()
        self.summary = self._generate_summary_placeholder()
        
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
        """Try to find and process via Listen Notes."""
        title = self.episode_info.get('title', '')
        show_name = self.episode_info.get('show_name', '')
        
        # Set language for Listen Notes search
        ln_language = "Japanese" if language in ['ja', 'Japanese'] else "English"
        self.listen_notes_client.set_language(ln_language)
        
        # Search for episode
        print(f"\n🔍 Searching: {show_name} - {title}")
        ln_url = self.listen_notes_client.get_episode_url(title, show_name)
        
        if not ln_url:
            print("❌ Episode not found on Listen Notes")
            
            # Try searching local downloads
            local_file = self._find_local_audio()
            if local_file:
                print(f"✅ Found local file: {local_file}")
                return self._transcribe_with_whisper(str(local_file), language, whisper_model)
            
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
                return None
            
            print(f"✅ Downloaded: {downloaded_file}")
            print(f"   Size: {verification['file_size'] / (1024*1024):.1f}MB")
            
            # Transcribe with Whisper
            return self._transcribe_with_whisper(str(downloaded_file), language, whisper_model)
            
        except Exception as e:
            print(f"❌ Download error: {e}")
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
    
    def _save_output(self, spotify_url: str) -> Path:
        """Save the processed content to markdown file."""
        title = self.episode_info.get('title', 'Unknown')
        safe_title = title.replace('/', '／').replace(':', '：').replace('?', '？')
        
        output_dir = Path('data/outputs') / safe_title
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / 'episode_summary.md'
        
        duration_str = self._format_duration(self.episode_info.get('duration_ms'))
        
        content = f"""## **Basic Information**
- Spotify URL: [Episode Link]({spotify_url})
- Podcast: {self.episode_info.get('show_name', 'N/A')}
- Release Date: {self.episode_info.get('release_date', 'N/A')}
- Duration: {duration_str}

## **Summary**

{self.summary}

## **Chapters**

{self.chapters}

## **Transcript**

{self.transcript}
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
                duration_minutes=duration_minutes
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

