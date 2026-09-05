# 🎧 Podcast Notes Automation System

**Spotify URL や MP3 ファイルからポッドキャストを自動で文字起こし・要約・構造化ノート生成するシステム**

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

## 🌟 主な機能

- **🎵 Spotify 統合**: Spotify URL からメタデータ・カバー画像取得
- **🔍 Listen Notes 検索**: 音声ファイル自動検索・ダウンロード
- **🍎 iTunes/RSS フォールバック**: Apple Podcast経由でRSSから音声取得（Listen Notes失敗時）
- **🎙️ Whisper 文字起こし**: ローカルで高精度な音声認識（日本語・英語対応）
- **📄 Spotify HTML 抽出**: 「聴きながら読む」からの文字起こし取得（最終フォールバック）
- **📝 Claude チャプター生成**: AIによる高品質なチャプター目次・要約
- **☁️ Notion 連携**: 自動でデータベースに登録（カバー画像含む）
- **📱 iPhone から実行**: Spotify URL と追加の依頼をスマホから投げる（[docs/REMOTE_APP.md](docs/REMOTE_APP.md)）

## ⚡ クイックスタート

### 1. 依存関係インストール

```bash
# 基本依存関係
pip install -r requirements.txt

# Whisper（ローカル文字起こし用）
pip install openai-whisper

# Ollama（ローカル要約用 - オプション）
brew install ollama
ollama pull llama3.2
```

### 2. 設定ファイル

`config/config.yaml` を作成：

```yaml
spotify:
  client_id: 'your_spotify_client_id'
  client_secret: 'your_spotify_client_secret'
listen_notes:
  api_key: 'your_listen_notes_api_key'
gemini:
  api_key: 'your_gemini_api_key'
notion:
  api_key: 'your_notion_api_key'
  database_id: 'your_notion_database_id'
# Optional: default LLM for Summary / Key Takeaways / Chapters
llm:
  backend: gemini   # or lmstudio
lmstudio:
  base_url: 'http://localhost:1234/v1'
  model: 'google/gemma-4-e4b'
```

### 3. 処理実行

```bash
# 統合スクリプト（推奨）— 要約はデフォルトで Gemini
python process_unified.py "https://open.spotify.com/episode/xxx"

# ローカル LM Studio（OpenAI互換）に切り替え。Notion前に人力チェックするなら --no-notion
python process_unified.py "https://open.spotify.com/episode/xxx" --llm-backend lmstudio --no-notion
# LM Studio は context-length を十分に（例: 16384）。デフォルト4096だと長いチャンクで空応答になる。

# Spotify HTMLから処理
python process_spotify_transcript.py transcript.html "https://open.spotify.com/episode/xxx"

# ローカル音声ファイルから処理
python local_transcriber/process.py audio.mp3 --spotify-url "https://..."
```

## 📁 プロジェクト構造

```
podcast_notes_automation/
├── 🎯 scripts/              # 実行スクリプト
├── 🔧 core/                 # コア処理ロジック
│   ├── processors/          # メイン処理器
│   └── transcription/       # 文字起こしエンジン
├── 🔌 integrations/         # 外部API統合
├── 💾 database/             # データベース管理
├── 🌐 web/                  # Web インターフェース
├── 📡 server/               # iPhone 用ジョブサーバ
├── 📱 ios/                  # iPhone アプリ（SwiftUI）
├── 🧪 tests/                # テストファイル
├── ⚙️  config/               # 設定・依存関係
├── 📊 data/                 # データファイル
└── 📖 docs/                 # ドキュメント
```

## 🚀 使用方法

### 処理フロー概要

```
┌─────────────────────────────────────────────────────────────┐
│                    Spotify URL                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Listen Notes 音声検索                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │ 見つかった                 │ 見つからない
         ▼                           ▼
┌─────────────────┐     ┌─────────────────────────────────────┐
│ 音声ダウンロード │     │ iTunes/RSS フォールバック（自動）   │
└────────┬────────┘     │ 1. iTunes Search APIで番組検索      │
         │              │ 2. RSSフィードからエピソード検索    │
         │              │ 3. 音声URLを取得・ダウンロード      │
         │              └──────────────────┬──────────────────┘
         │                                 │
         │              ┌──────────────────┴──────────────────┐
         │              │ 見つかった        │ 見つからない     │
         │              ▼                   ▼                  │
         │     ┌─────────────────┐   ┌─────────────────────┐  │
         │     │ 音声ダウンロード │   │ Spotify HTML取得    │  │
         │     └────────┬────────┘   │（手動フォールバック）│  │
         │              │            └──────────┬──────────┘  │
         │              │                       │              │
         └──────────────┼───────────────────────┘              │
                        ▼                                      │
┌─────────────────────────────────────────────────────────────┐
│              Whisper文字起こし / HTML抽出                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Claude: チャプター・要約生成                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Notion登録（カバー画像含む）                   │
└─────────────────────────────────────────────────────────────┘
```

### 🍎 iTunes/RSS フォールバック（v3.1.0 新機能）

Listen Notesでエピソードが見つからない場合、自動的にiTunes/RSSフォールバックが実行されます：

1. **iTunes Search API**: 番組名でApple Podcastを検索（無料・認証不要）
2. **iTunes Lookup API**: Podcast IDからRSSフィードURLを取得
3. **RSS解析**: フィードからエピソードの音声URLを抽出
4. **ダウンロード＆文字起こし**: 通常フローと同じ

**対応条件**: Apple Podcastに登録されているポッドキャスト（Spotify独占配信は非対応）

### 🎯 AIアシスタントへの推奨プロンプト

新しいチャットでエピソード処理を依頼する際は、以下の指示文を使用してください：

```
以下のSpotifyエピソードを処理してNotionに追加してください：

Spotify URL: [URL]

処理フロー：
1. Listen Notesで音声検索 → Whisper文字起こし
2. 見つからない場合: Browser MCPでSpotify HTMLを取得
3. それも失敗した場合: 諦めて報告

※チャプター目次・要約・Notion登録まで一括でお願いします
```

### 🔍 ワークフローA: 完全自動（推奨）

```bash
python process_unified.py "https://open.spotify.com/episode/xxx"
```

**自動フォールバック順序**:
1. Listen Notes検索 → 見つかれば音声ダウンロード
2. iTunes/RSS検索 → Apple Podcastから音声取得
3. 両方失敗 → 手動フォールバックの案内

**特徴**:
- ✅ 音声から直接文字起こしするため精度が高い
- ✅ ほぼ完全自動化（Apple Podcastに登録されていれば）
- ⚠️ Spotify独占配信の場合は手動フォールバック必要

### 📄 ワークフローB: Spotify HTML（手動フォールバック）

自動検索がすべて失敗した場合、Spotifyの「聴きながら読む」機能を使用：

1. **Browser MCPでSpotify URLを開く**
2. **「聴きながら読む」からHTMLを取得**
3. **以下のコマンドで処理**：

```bash
python process_spotify_transcript.py transcript.html "https://open.spotify.com/episode/xxx"
```

**特徴**:
- ✅ Spotify独占配信でも処理可能
- ✅ ほぼすべてのSpotifyエピソードに対応
- ⚠️ Spotify側の文字起こし品質に依存

## 📝 スクリプト詳細

### `process_unified.py` - 統合処理スクリプト（推奨）

```bash
# 基本使用
python process_unified.py "https://open.spotify.com/episode/xxx"

# 言語指定
python process_unified.py "https://open.spotify.com/episode/xxx" --language ja

# Spotify HTMLから処理（フォールバック）
python process_unified.py "https://open.spotify.com/episode/xxx" --html-file transcript.html

# ローカル音声ファイルから処理
python process_unified.py "https://open.spotify.com/episode/xxx" --audio-file episode.mp3

# Notion登録をスキップ
python process_unified.py "https://open.spotify.com/episode/xxx" --no-notion
```

### `process_spotify_transcript.py` - Spotify HTML処理

```bash
python process_spotify_transcript.py <HTMLファイル> "<Spotify URL>"
```

### `local_transcriber/process.py` - ローカル音声処理

```bash
python local_transcriber/process.py <音声ファイル> --language ja --spotify-url "<URL>"
```

### 処理フローの詳細

1. **Spotifyからメタデータ取得**: タイトル、番組名、公開日、カバー画像URL
2. **音声ファイル取得**（自動フォールバック）:
   - **Step 1**: Listen Notes APIでエピソードを検索
   - **Step 2**: 見つからない場合 → iTunes Search APIで番組検索 → RSSから音声URL取得
   - **Step 3**: それも失敗 → ローカル`data/downloads/`を検索
   - **Step 4**: すべて失敗 → 手動フォールバックの案内（Spotify HTML）
3. **文字起こし処理**:
   - 音声の場合：Whisper（ローカル）で高精度文字起こし
   - HTMLの場合：BeautifulSoupで抽出・整形
4. **チャプター・要約生成**:
   - Claudeが対話的に最適なチャプター目次と要約を生成
5. **結果保存**:
   - `data/outputs/[エピソードタイトル]/episode_summary.md`に保存
6. **Notionアップロード**:
   - 全文をNotionデータベースに追加（100ブロック制限を自動回避）
   - カバー画像、Spotify URL、番組名などのメタデータも設定

### 注意事項

- Whisper処理は音声の長さに応じて数分〜数十分かかります
- Listen Notesで見つからない場合は、Browser MCPまたは手動でHTMLを取得してください
- 長い文字起こしも100ブロックずつ分割してNotionに全文アップロードされます

## 🔧 開発・カスタマイズ

### テスト実行

```bash
# 統合テスト
python -m pytest tests/integration/

# 単体テスト
python -m pytest tests/unit/

# デバッグ
python tests/debug/debug_sections.py
```

### コードフォーマット

```bash
black .
flake8 .
```

## 📊 システム概要

### 処理フロー

1. **入力**: Spotify URL
2. **メタデータ取得**: Spotify API でタイトル・カバー画像取得
3. **音声取得**: Listen Notes API 経由（失敗時はSpotify HTML）
4. **文字起こし**: Whisper（ローカル）で高精度変換
5. **AI 処理**: Claude でチャプター・要約生成
6. **保存**: Markdown ファイル + Notion データベース

### アーキテクチャ

```
podcast-notes-automation/
├── process_unified.py          # 統合処理スクリプト（推奨）
├── process_spotify_transcript.py # Spotify HTML処理
├── process_episode.py          # レガシー処理スクリプト
├── src/
│   ├── spotify.py              # Spotify API
│   ├── listen_notes.py         # Listen Notes API
│   ├── utils.py                # ユーティリティ
│   └── integrations/
│       ├── notion_client.py    # Notion API
│       └── itunes_rss.py       # iTunes/RSS フォールバック (v3.1.0)
├── local_transcriber/          # ローカル文字起こし
│   ├── transcriber.py          # Whisper
│   ├── summarizer.py           # Ollama (オプション)
│   └── process.py              # 処理スクリプト
├── config/
│   └── config.yaml             # API設定
└── data/
    ├── downloads/              # ダウンロード音声
    └── outputs/                # 処理結果
```

## 📈 現在の状況

✅ **Whisper対応**: ローカル文字起こし（日本語・英語）  
✅ **Notion連携**: 全文アップロード（100ブロック制限回避）  
✅ **iTunes/RSS**: Listen Notes失敗時の自動フォールバック（無料API）  
✅ **Spotify HTML**: iTunes/RSS失敗時の手動フォールバック  
✅ **日英対応**: 完了

## 📖 詳細ドキュメント

- [📋 セットアップガイド](docs/setup/)
- [🎯 使用方法ガイド](docs/guides/)
- [⚙️ 開発者向け](docs/development/)

## 🤝 コントリビューション

1. Fork プロジェクト
2. Feature ブランチ作成 (`git checkout -b feature/AmazingFeature`)
3. 変更をコミット (`git commit -m 'Add AmazingFeature'`)
4. ブランチにプッシュ (`git push origin feature/AmazingFeature`)
5. Pull Request 作成

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルを参照

## 🔗 関連リンク

- [Spotify Web API](https://developer.spotify.com/documentation/web-api/)
- [Listen Notes API](https://www.listennotes.com/api/)
- [Google Gemini AI](https://ai.google.dev/)
- [Streamlit](https://streamlit.io/)

---

**作成**: 2024 年 12 月 | **更新**: 2026 年 5 月 | **バージョン**: 3.1.1

### v3.1.2 変更点 (2026-05-06)
- 📝 **教訓記録**: ep #382 で日本語音声が英語として文字起こしされた事故を反省として記録。
- **原因**: Spotify APIが返すエピソードの `language` メタデータ（配信者が手動設定）が `en` で誤登録されていた。`process_unified.py` はこれを盲信して Whisper に `language="en"` で渡してしまった。
- **なぜ深刻か**: Whisperの `language` 引数は **ヒントではなく強制指定**。間違った言語コードを渡すと、auto-detectは行われず、音を強制的にその言語の単語に当てはめる挙動になり、読めない英訳もどきが生成される（自動検出ミスではない）。
- **対策**:
  - `process_unified.py` 起動時に言語ソース（CLI / Spotifyメタ）を明示ログ出力し、メタ由来の場合は誤タグ可能性を警告。
  - `src/spotify.py` の `language` 取得箇所にコメントで誤登録リスクを明記。
  - 文字起こし結果がおかしい時は `--language ja|en` で明示再実行する運用に。
- **今後の改善余地**: Whisperにあえて `language=None` を渡して auto-detect させる選択肢、または説明文の文字種からヒューリスティック検証を入れる。

### v3.1.1 変更点 (2026-05-03)
- 🐛 **Critical bugfix**: `google-genai` パッケージ未インストール時、Gemini呼び出しが全失敗 → Summary/Key Takeaways/Timestamps が無音でプレースホルダーや生の文字起こし片に置換されていた。
- 📦 ルートに `requirements.txt` を新設し `google-genai` を必須依存として明記。
- 🚨 `process_unified.py` の `_init_gemini` を改修。Gemini が未初期化の場合は明示的な警告を表示する（無音で続行しない）。
- ✅ 影響: Jenny Wenエピソード以降の9件は再処理が必要（旧ページはアーカイブ）。
- **教訓**: LLM呼び出しを「あったら使う」式の optional にすると失敗が無音化する。必須依存はrequirements.txtにピン留めし、初期化失敗は冒頭で警告を出すべし。

### v3.1.0 変更点 (2026-01-05)
- 🍎 **iTunes/RSSフォールバック**: Listen Notes失敗時に自動でApple Podcast経由で音声取得
- iTunes Search API・Lookup API（無料・認証不要）でRSSフィードURL取得
- RSSパースで該当エピソードの音声URLを自動抽出
- 追加の依存関係なし（標準ライブラリのみ使用）

### v3.0.0 変更点
- `process_unified.py`: 統合処理スクリプト追加
- Whisperローカル文字起こし対応
- Browser MCPフォールバック対応
- Summary.fm依存を完全排除
- Notion 100ブロック制限回避
