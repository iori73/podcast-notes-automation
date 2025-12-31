"""
Local summarization module using Ollama (local LLM).
Generates summaries from transcription text without external API dependencies.
"""

import sys
import subprocess
import json
from pathlib import Path

# Add parent src directory to path for shared utilities
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir / "src"))


def check_ollama_available():
    """Check if Ollama is installed and running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def ollama_generate(prompt, model="llama3.2", timeout=120):
    """
    Generate text using Ollama CLI.
    
    Args:
        prompt: The prompt to send to the model
        model: Model name (default: llama3.2)
        timeout: Timeout in seconds
    
    Returns:
        str: Generated text or None on error
    """
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"⚠️ Ollama error: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print(f"⚠️ Ollama timeout after {timeout}s")
        return None
    except Exception as e:
        print(f"⚠️ Ollama error: {str(e)}")
        return None


class OllamaSummarizer:
    """
    Generate summaries using local Ollama LLM.
    
    No API limits, no rate limits, completely free and offline.
    """
    
    def __init__(self, model="llama3.2"):
        """
        Initialize Ollama summarizer.
        
        Args:
            model: Ollama model to use (default: llama3.2)
        """
        self.model = model
        
        if not check_ollama_available():
            raise RuntimeError(
                "Ollama is not available. Please install Ollama:\n"
                "  brew install ollama\n"
                "  ollama pull llama3.2"
            )
        
        print(f"✅ Ollama initialized: {model}")
    
    def generate_summary(self, transcript, language="ja", max_length=300):
        """
        Generate a summary of the transcript.
        
        Args:
            transcript: Full text transcription
            language: "ja" for Japanese, "en" for English
            max_length: Target summary length in characters
        
        Returns:
            str: Generated summary
        """
        print(f"📝 Generating summary ({language}) with Ollama...")
        
        # Truncate transcript if too long (Ollama context limit)
        max_input = 6000
        if len(transcript) > max_input:
            transcript = transcript[:max_input] + "..."
        
        if language == "ja":
            prompt = f"""以下のポッドキャストの文字起こしを{max_length}文字程度で日本語で要約してください。

要約のガイドライン:
- 主要なトピックと議論のポイントを含める
- 話者の重要な主張や結論を含める
- 読みやすい自然な日本語で書く
- 箇条書きではなく、段落形式で書く
- 要約のみを出力し、他の説明は不要

文字起こし:
{transcript}

要約:"""
        else:
            prompt = f"""Please summarize the following podcast transcript in about {max_length} characters.

Summary guidelines:
- Include main topics and key discussion points
- Highlight important claims and conclusions
- Write in natural, readable English
- Use paragraph format, not bullet points
- Output only the summary, no other explanation

Transcript:
{transcript}

Summary:"""
        
        result = ollama_generate(prompt, self.model, timeout=180)
        
        if result:
            print(f"✅ Summary generated ({len(result)} chars)")
            return result
        else:
            return "Summary generation failed"
    
    def generate_chapter_titles(self, timestamps_text, transcript, language="ja"):
        """
        Generate better chapter titles from timestamps.
        
        Args:
            timestamps_text: Existing timestamps with raw text
            transcript: Full transcription for context
            language: "ja" or "en"
        
        Returns:
            str: Improved timestamps with better titles
        """
        print(f"📑 Generating chapter titles ({language}) with Ollama...")
        
        # Truncate if needed
        if len(transcript) > 3000:
            transcript = transcript[:3000] + "..."
        
        if language == "ja":
            prompt = f"""以下のポッドキャストのタイムスタンプを改善してください。
各タイムスタンプに、その時間帯の内容を表す簡潔なタイトル（15-30文字）をつけてください。

現在のタイムスタンプ:
{timestamps_text}

出力形式（これだけを出力）:
MM:SS タイトル
MM:SS タイトル
...

タイムスタンプのみを出力してください:"""
        else:
            prompt = f"""Please improve the following podcast timestamps.
Add concise titles (15-30 characters) that describe the content at each timestamp.

Current timestamps:
{timestamps_text}

Output format (only this):
MM:SS Title
MM:SS Title
...

Output only the timestamps:"""
        
        result = ollama_generate(prompt, self.model, timeout=120)
        
        if result:
            print(f"✅ Chapter titles generated")
            return result
        else:
            return timestamps_text
    
    def translate_to_english(self, text, text_type="summary"):
        """
        Translate Japanese text to English.
        
        Args:
            text: Japanese text to translate
            text_type: "summary" or "transcript" for context
        
        Returns:
            str: English translation
        """
        print(f"🌐 Translating {text_type} to English with Ollama...")
        
        # Truncate if too long
        max_input = 4000
        if len(text) > max_input:
            text = text[:max_input] + "..."
        
        prompt = f"""Translate the following Japanese text to natural English.
Preserve the meaning and context accurately.
Output only the translation, no other text.

Japanese text:
{text}

English translation:"""
        
        result = ollama_generate(prompt, self.model, timeout=180)
        
        if result:
            print(f"✅ Translation complete ({len(result)} chars)")
            return result
        else:
            return "*Translation unavailable*"


def main():
    """Test the summarizer."""
    summarizer = OllamaSummarizer()
    
    test_text = """
    今回は、ポッドキャストの自動要約システムについて話しています。
    Whisperを使った文字起こしと、ローカルLLMを使った要約生成を組み合わせることで、
    効率的にポッドキャストの内容を整理することができます。
    このシステムは完全にローカルで動作し、外部サービスに依存しません。
    """
    
    summary = summarizer.generate_summary(test_text, language="ja")
    print(f"\nGenerated Summary:\n{summary}")


if __name__ == "__main__":
    main()
