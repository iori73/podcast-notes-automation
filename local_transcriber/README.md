# Local Podcast Transcriber

外部サービス（Summary.fm、Gemini API）に依存せず、**完全にローカル**で動作するポッドキャスト文字起こし・要約システム。

## Features

- **Whisper**: OpenAI の音声認識モデルを使用した高精度な文字起こし
- **Ollama**: ローカルLLM（Llama 3.2）を使用した要約生成（制限なし・無料）
- **Notion連携**: 自動でNotionデータベースにアップロード
- **多言語対応**: 日本語・英語に対応（自動検出も可能）
- **タイムスタンプ生成**: 自動でチャプター形式のタイムスタンプを生成
- **英訳機能**: 日本語コンテンツの英語翻訳

## Architecture

```
Audio File (MP3)
       ↓
  [Whisper] ← ローカル（制限なし）
       ↓
 Transcription + Timestamps
       ↓
  [Ollama/Llama] ← ローカル（制限なし）
       ↓
 Summary + Chapter Titles
       ↓
  [Notion API]
       ↓
 Podcast Notes Database
```

## Requirements

### System Requirements

- Python 3.9+
- FFmpeg（音声処理用）
- Ollama（ローカルLLM）
- 8GB+ RAM（推奨）
- GPU（オプション、処理速度向上）

### Installation

```bash
# 1. FFmpeg
brew install ffmpeg

# 2. Ollama
brew install ollama
ollama pull llama3.2

# 3. Python dependencies
cd local_transcriber
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# 自動言語検出
python process.py ../data/downloads/episode.mp3

# 日本語を指定
python process.py ../data/downloads/episode.mp3 --language ja

# 英語を指定
python process.py ../data/downloads/episode.mp3 --language en
```

### With Metadata (Recommended)

```bash
python process.py ../data/downloads/episode.mp3 \
    --language ja \
    --spotify-url "https://open.spotify.com/episode/xxx" \
    --release-date "2024-01-15" \
    --duration "30:00" \
    --podcast-name "Takram Cast"
```

### Skip Options

```bash
# Notion登録をスキップ
python process.py audio.mp3 --no-notion

# 要約生成をスキップ（文字起こしのみ）
python process.py audio.mp3 --no-summary

# 英訳をスキップ
python process.py audio.mp3 --no-translation
```

### All Options

| Option | Description | Default |
|--------|-------------|---------|
| `--language`, `-l` | 言語: `ja`, `en`, `auto` | `auto` |
| `--model-size` | Whisperモデル: `tiny`, `base`, `small`, `medium`, `large` | `medium` |
| `--ollama-model` | Ollamaモデル | `llama3.2` |
| `--spotify-url` | Spotify エピソード URL | None |
| `--release-date` | 公開日 (YYYY-MM-DD) | None |
| `--duration` | 再生時間 (MM:SS) | None |
| `--podcast-name` | ポッドキャスト名 | None |
| `--cover-url` | カバー画像URL | None |
| `--output-dir` | 出力先ディレクトリ | `../data/outputs/<episode>/` |
| `--no-summary` | 要約生成をスキップ | False |
| `--no-translation` | 英訳をスキップ | False |
| `--no-notion` | Notion登録をスキップ | False |

## Output Format

既存システムと同じ形式で `data/outputs/` に保存され、Notionにアップロードされます：

```markdown
## **Basic Information**

- Spotify URL: [Episode Link](...)
- Release Date: MM/DD/YYYY
- Duration: MM:SS

## **Summary**

(Ollama/Llama3.2 による要約)

## **Timestamps**

00:00 イントロダクション
01:00 メインテーマ
...

## **Transcript**

(Whisper による文字起こし)

## **English Summary**

(日本語エピソードのみ)

## **English Transcription**

(日本語エピソードのみ)
```

## Processing Time

| Audio Length | Whisper (CPU) | Ollama Summary | Total |
|--------------|--------------|----------------|-------|
| 10 min | 2-5 min | 30s-1min | ~6 min |
| 30 min | 5-15 min | 1-2 min | ~17 min |
| 60 min | 10-30 min | 2-3 min | ~33 min |

## Comparison

| Feature | Summary.fm | Gemini API | Local Transcriber |
|---------|-----------|-----------|-------------------|
| Cost | 月5回無料 | 従量課金/制限あり | **完全無料** |
| Rate Limit | 月5回 | あり | **なし** |
| Internet | 必要 | 必要 | **不要** |
| Privacy | サーバー送信 | サーバー送信 | **ローカル処理** |
| Notion連携 | あり | なし | **あり** |

## Troubleshooting

### "Ollama not available"

```bash
# Ollamaをインストール
brew install ollama

# モデルをダウンロード
ollama pull llama3.2

# Ollamaサービスを起動
ollama serve
```

### "No module named 'whisper'"

```bash
pip install openai-whisper
```

### Notion upload fails

`config/config.yaml` に正しいNotion API keyとDatabase IDが設定されているか確認：

```yaml
notion:
  api_key: "secret_xxx"
  database_id: "xxx"
```

## License

This project uses:
- [OpenAI Whisper](https://github.com/openai/whisper) - MIT License
- [Ollama](https://ollama.ai/) - MIT License
- [Notion API](https://developers.notion.com/) - Notion Terms of Service
