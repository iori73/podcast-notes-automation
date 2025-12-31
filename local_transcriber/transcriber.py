"""
Whisper-based local transcription module.
Provides speech-to-text and timestamp generation without external services.
"""

import whisper
from pathlib import Path
from datetime import timedelta


class WhisperTranscriber:
    """
    Local transcription using OpenAI Whisper.
    
    Supported languages:
    - Japanese (ja)
    - English (en)
    - Auto-detection (None)
    """
    
    def __init__(self, model_size="medium"):
        """
        Initialize the Whisper model.
        
        Args:
            model_size: Model size to use. Options:
                - "tiny": Fastest, least accurate (~1GB VRAM)
                - "base": Fast, decent accuracy (~1GB VRAM)
                - "small": Good balance (~2GB VRAM)
                - "medium": High accuracy (~5GB VRAM) [Recommended]
                - "large": Best accuracy (~10GB VRAM)
        """
        print(f"🔄 Loading Whisper model: {model_size}...")
        print("   (This may take a few minutes on first run)")
        self.model = whisper.load_model(model_size)
        self.model_size = model_size
        print(f"✅ Whisper model '{model_size}' loaded successfully")
    
    def transcribe(self, audio_path, language=None):
        """
        Transcribe an audio file.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, M4A, etc.)
            language: Language code ("ja" for Japanese, "en" for English)
                     If None, auto-detects language.
        
        Returns:
            dict: {
                "transcription": Full text transcription,
                "timestamps": Formatted timestamps (MM:SS Topic),
                "segments": Raw segment data from Whisper,
                "language": Detected or specified language
            }
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        print(f"🎙️ Starting transcription: {audio_path.name}")
        print(f"   Language: {language if language else 'Auto-detect'}")
        print(f"   Model: {self.model_size}")
        print("   This may take several minutes...")
        
        # Transcribe with Whisper
        result = self.model.transcribe(
            str(audio_path),
            language=language,
            verbose=False,  # Disable Whisper's own progress output
            task="transcribe"
        )
        
        detected_language = result.get("language", language)
        print(f"✅ Transcription complete!")
        print(f"   Detected language: {detected_language}")
        print(f"   Total segments: {len(result['segments'])}")
        
        # Format timestamps
        timestamps = self._format_timestamps(result["segments"])
        
        return {
            "transcription": result["text"].strip(),
            "timestamps": timestamps,
            "segments": result["segments"],
            "language": detected_language
        }
    
    def _format_timestamps(self, segments, group_interval=60):
        """
        Format Whisper segments into readable timestamps.
        
        Groups segments by time intervals and creates chapter-like timestamps.
        
        Args:
            segments: List of segment dictionaries from Whisper
            group_interval: Seconds between timestamp markers (default: 60)
        
        Returns:
            str: Formatted timestamps in "MM:SS Topic" format
        """
        if not segments:
            return "No timestamps available"
        
        timestamps = []
        current_group_start = 0
        current_group_text = []
        
        for segment in segments:
            start_time = segment["start"]
            text = segment["text"].strip()
            
            # Check if we should start a new group
            if start_time >= current_group_start + group_interval:
                # Save the previous group
                if current_group_text:
                    time_str = self._format_time(current_group_start)
                    # Get first meaningful phrase as topic
                    topic = self._extract_topic(current_group_text)
                    timestamps.append(f"{time_str} {topic}")
                
                # Start new group
                current_group_start = int(start_time / group_interval) * group_interval
                current_group_text = [text]
            else:
                current_group_text.append(text)
        
        # Don't forget the last group
        if current_group_text:
            time_str = self._format_time(current_group_start)
            topic = self._extract_topic(current_group_text)
            timestamps.append(f"{time_str} {topic}")
        
        return "\n".join(timestamps)
    
    def _format_time(self, seconds):
        """Convert seconds to MM:SS format."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def _extract_topic(self, texts):
        """
        Extract a meaningful topic from a group of text segments.
        
        Args:
            texts: List of text strings from segments
        
        Returns:
            str: A short topic description (max 50 chars)
        """
        # Combine all texts
        combined = " ".join(texts)
        
        # Clean up and truncate
        combined = combined.replace("\n", " ").strip()
        
        # Get first sentence or first N characters
        if "。" in combined:
            topic = combined.split("。")[0] + "。"
        elif ". " in combined:
            topic = combined.split(". ")[0] + "."
        else:
            topic = combined
        
        # Truncate if too long
        if len(topic) > 50:
            topic = topic[:47] + "..."
        
        return topic


def main():
    """Test the transcriber with a sample file."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python transcriber.py <audio_file> [language]")
        print("  language: 'ja' for Japanese, 'en' for English, or omit for auto-detect")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else None
    
    transcriber = WhisperTranscriber(model_size="medium")
    result = transcriber.transcribe(audio_path, language=language)
    
    print("\n" + "=" * 50)
    print("TRANSCRIPTION RESULT")
    print("=" * 50)
    print(f"\nLanguage: {result['language']}")
    print(f"\nTimestamps:\n{result['timestamps']}")
    print(f"\nTranscription (first 500 chars):\n{result['transcription'][:500]}...")


if __name__ == "__main__":
    main()

