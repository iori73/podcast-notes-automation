#!/usr/bin/env python3
"""
Local Podcast Transcription and Summarization

This script processes podcast audio files locally using:
- OpenAI Whisper for transcription and timestamps
- Ollama (local LLM) for summary generation
- Notion API for database upload

Usage:
    python process.py <audio_file> [options]

Examples:
    # Basic usage (auto-detect language)
    python process.py ../data/downloads/episode.mp3
    
    # Specify language
    python process.py ../data/downloads/episode.mp3 --language ja
    
    # With Spotify URL for metadata
    python process.py ../data/downloads/episode.mp3 --language ja --spotify-url "https://open.spotify.com/episode/..."
    
    # Skip Notion upload
    python process.py ../data/downloads/episode.mp3 --language ja --no-notion
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent directories to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir / "src"))
sys.path.insert(0, str(parent_dir / "src" / "integrations"))

from transcriber import WhisperTranscriber
from summarizer import OllamaSummarizer


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Local podcast transcription and summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python process.py ../data/downloads/episode.mp3
    python process.py ../data/downloads/episode.mp3 --language ja
    python process.py ../data/downloads/episode.mp3 --language ja --spotify-url "https://..."
        """
    )
    
    parser.add_argument(
        "audio_file",
        type=str,
        help="Path to the audio file (MP3, WAV, M4A, etc.)"
    )
    
    parser.add_argument(
        "--language", "-l",
        type=str,
        choices=["ja", "en", "auto"],
        default="auto",
        help="Audio language: 'ja' (Japanese), 'en' (English), or 'auto' (default: auto)"
    )
    
    parser.add_argument(
        "--spotify-url",
        type=str,
        default=None,
        help="Spotify episode URL for metadata"
    )
    
    parser.add_argument(
        "--release-date",
        type=str,
        default=None,
        help="Release date (YYYY-MM-DD format)"
    )
    
    parser.add_argument(
        "--duration",
        type=str,
        default=None,
        help="Episode duration (MM:SS format)"
    )
    
    parser.add_argument(
        "--podcast-name",
        type=str,
        default=None,
        help="Podcast name for Notion"
    )
    
    parser.add_argument(
        "--cover-url",
        type=str,
        default=None,
        help="Cover image URL for Notion"
    )
    
    parser.add_argument(
        "--model-size",
        type=str,
        choices=["tiny", "base", "small", "medium", "large"],
        default="medium",
        help="Whisper model size (default: medium)"
    )
    
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="llama3.2",
        help="Ollama model for summarization (default: llama3.2)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: ../data/outputs/<episode_name>/)"
    )
    
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip summary generation (transcription only)"
    )
    
    parser.add_argument(
        "--no-translation",
        action="store_true",
        help="Skip English translation for Japanese episodes"
    )
    
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="Skip Notion upload"
    )
    
    return parser.parse_args()


def format_date(date_str):
    """Format date string to MM/DD/YYYY."""
    if not date_str:
        return ""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%m/%d/%Y")
    except:
        return date_str


def parse_duration_to_minutes(duration_str):
    """Parse duration string (MM:SS or HH:MM:SS) to minutes."""
    if not duration_str:
        return None
    try:
        parts = duration_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60
        elif len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        return None
    except:
        return None


def save_output(output_dir, result, metadata, include_translation=True):
    """Save the transcription result to markdown file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "episode_summary.md"
    
    with open(output_file, "w", encoding="utf-8") as f:
        # Basic Information
        f.write("## **Basic Information**\n\n")
        
        if metadata.get("spotify_url"):
            f.write(f"- Spotify URL: [Episode Link]({metadata['spotify_url']})\n")
        else:
            f.write("- Spotify URL: [Episode Link]()\n")
        
        f.write(f"- Release Date: {format_date(metadata.get('release_date', ''))}\n")
        f.write(f"- Duration: {metadata.get('duration', '')}\n")
        
        # Summary
        f.write("\n## **Summary**\n\n")
        f.write(result.get("summary", "Summary not available"))
        
        # Timestamps
        f.write("\n\n## **Timestamps**\n\n")
        f.write(result.get("timestamps", "Timestamps not available"))
        
        # Transcript
        f.write("\n\n## **Transcript**\n\n")
        f.write(result.get("transcription", "Transcription not available"))
        f.write("\n")
        
        # English translations (for Japanese content)
        if include_translation and result.get("language") == "ja":
            f.write("\n## **English Summary**\n\n")
            f.write(result.get("english_summary", "*Translation unavailable*"))
            f.write("\n\n")
            
            f.write("\n## **English Transcription**\n\n")
            f.write(result.get("english_transcription", "*Translation unavailable*"))
            f.write("\n")
    
    return output_file


def fetch_spotify_metadata(spotify_url):
    """Fetch metadata from Spotify URL."""
    try:
        from spotify import SpotifyClient
        
        print(f"🎵 Fetching Spotify metadata...")
        spotify = SpotifyClient()
        info = spotify.get_episode_info(spotify_url)
        
        if info:
            return {
                "cover_url": info.get("cover_image_url"),
                "podcast_name": info.get("show_name"),
                "release_date": info.get("release_date"),
                "duration": f"{int(info.get('duration_ms', 0) / 1000 / 60)}:00"
            }
        return {}
    except Exception as e:
        print(f"⚠️ Spotify fetch error: {str(e)}")
        return {}


def upload_to_notion(output_file, metadata, result):
    """Upload the episode to Notion database."""
    try:
        from notion_client import NotionClient
        
        print("\n📤 Uploading to Notion...")
        
        # Read the markdown content
        with open(output_file, "r", encoding="utf-8") as f:
            markdown_content = f.read()
        
        # Get title from file path
        title = output_file.parent.name
        
        # Parse duration to minutes
        duration_minutes = parse_duration_to_minutes(metadata.get("duration"))
        
        # Create Notion client and upload
        notion = NotionClient()
        page_id = notion.create_page(
            title=title,
            markdown_content=markdown_content,
            spotify_url=metadata.get("spotify_url"),
            cover_url=metadata.get("cover_url"),
            podcast_name=metadata.get("podcast_name"),
            release_date=metadata.get("release_date"),
            duration_minutes=duration_minutes
        )
        
        if page_id:
            print(f"✅ Notion upload complete!")
            return True
        else:
            print("❌ Notion upload failed")
            return False
            
    except ImportError:
        print("⚠️ Notion client not available. Skipping upload.")
        return False
    except Exception as e:
        print(f"❌ Notion upload error: {str(e)}")
        return False


def main():
    """Main processing function."""
    args = parse_args()
    
    # Validate audio file
    audio_path = Path(args.audio_file)
    if not audio_path.exists():
        print(f"❌ Error: Audio file not found: {audio_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("🎙️ LOCAL PODCAST TRANSCRIBER")
    print("   (Whisper + Ollama + Notion)")
    print("=" * 60)
    print(f"📁 Audio file: {audio_path.name}")
    print(f"🌐 Language: {args.language}")
    print(f"🤖 Whisper model: {args.model_size}")
    print(f"🦙 Ollama model: {args.ollama_model}")
    print("=" * 60)
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # Use ../data/outputs/<episode_name>/
        episode_name = audio_path.stem
        output_dir = parent_dir / "data" / "outputs" / episode_name
    
    print(f"📂 Output: {output_dir}")
    print()
    
    # Initialize transcriber
    print("=" * 60)
    print("STEP 1: Transcription (Whisper)")
    print("=" * 60)
    
    transcriber = WhisperTranscriber(model_size=args.model_size)
    
    # Transcribe
    language = None if args.language == "auto" else args.language
    transcription_result = transcriber.transcribe(str(audio_path), language=language)
    
    result = {
        "transcription": transcription_result["transcription"],
        "timestamps": transcription_result["timestamps"],
        "language": transcription_result["language"]
    }
    
    print(f"\n✅ Transcription complete!")
    print(f"   Characters: {len(result['transcription'])}")
    print(f"   Language: {result['language']}")
    
    # Generate summary using Ollama
    if not args.no_summary:
        print()
        print("=" * 60)
        print("STEP 2: Summary Generation (Ollama)")
        print("=" * 60)
        
        try:
            summarizer = OllamaSummarizer(model=args.ollama_model)
            
            # Generate summary
            summary_language = "ja" if result["language"] == "ja" else "en"
            result["summary"] = summarizer.generate_summary(
                result["transcription"],
                language=summary_language
            )
            
            # Improve timestamps with better titles
            result["timestamps"] = summarizer.generate_chapter_titles(
                result["timestamps"],
                result["transcription"],
                language=summary_language
            )
            
            # English translation for Japanese content
            if result["language"] == "ja" and not args.no_translation:
                print()
                print("=" * 60)
                print("STEP 3: English Translation (Ollama)")
                print("=" * 60)
                
                result["english_summary"] = summarizer.translate_to_english(
                    result["summary"], "summary"
                )
                
                # Only translate first part of transcript to save time
                transcript_preview = result["transcription"][:3000]
                result["english_transcription"] = summarizer.translate_to_english(
                    transcript_preview, "transcript"
                )
                if len(result["transcription"]) > 3000:
                    result["english_transcription"] += "\n\n*[Partial translation - full transcript above]*"
                    
        except Exception as e:
            print(f"⚠️ Summary generation error: {str(e)}")
            result["summary"] = "Summary generation failed"
    else:
        result["summary"] = "Summary skipped"
    
    # Prepare metadata
    metadata = {
        "spotify_url": args.spotify_url,
        "release_date": args.release_date,
        "duration": args.duration,
        "podcast_name": args.podcast_name,
        "cover_url": args.cover_url
    }
    
    # Auto-fetch metadata from Spotify if URL provided but other fields missing
    if args.spotify_url and (not args.cover_url or not args.podcast_name):
        print()
        print("=" * 60)
        print("FETCHING SPOTIFY METADATA")
        print("=" * 60)
        
        spotify_data = fetch_spotify_metadata(args.spotify_url)
        
        # Fill in missing metadata
        if not metadata.get("cover_url") and spotify_data.get("cover_url"):
            metadata["cover_url"] = spotify_data["cover_url"]
            print(f"   📷 Cover: {spotify_data['cover_url'][:50]}...")
        
        if not metadata.get("podcast_name") and spotify_data.get("podcast_name"):
            metadata["podcast_name"] = spotify_data["podcast_name"]
            print(f"   🎙️ Podcast: {spotify_data['podcast_name']}")
        
        if not metadata.get("release_date") and spotify_data.get("release_date"):
            metadata["release_date"] = spotify_data["release_date"]
            print(f"   📅 Date: {spotify_data['release_date']}")
        
        if not metadata.get("duration") and spotify_data.get("duration"):
            metadata["duration"] = spotify_data["duration"]
            print(f"   ⏱️ Duration: {spotify_data['duration']}")
    
    # Save output
    print()
    print("=" * 60)
    print("SAVING OUTPUT")
    print("=" * 60)
    
    include_translation = result.get("language") == "ja" and not args.no_translation
    output_file = save_output(output_dir, result, metadata, include_translation)
    
    print(f"✅ Output saved to: {output_file}")
    
    # Upload to Notion
    if not args.no_notion:
        print()
        print("=" * 60)
        print("STEP 4: Notion Upload")
        print("=" * 60)
        
        upload_to_notion(output_file, metadata, result)
    
    # Print summary stats
    print()
    print("=" * 60)
    print("📊 PROCESSING COMPLETE")
    print("=" * 60)
    print(f"📝 Transcription: {len(result['transcription'])} characters")
    print(f"📝 Summary: {len(result.get('summary', ''))} characters")
    print(f"📝 Timestamps: {result['timestamps'].count(chr(10)) + 1} chapters")
    print(f"📂 Output: {output_file}")
    if not args.no_notion:
        print(f"📤 Notion: Uploaded")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
