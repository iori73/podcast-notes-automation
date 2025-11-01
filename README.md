# 🎧 Podcast Notes Automation System

**Spotify URL や MP3 ファイルからポッドキャストを自動で文字起こし・要約・構造化ノート生成するシステム**

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

## 🌟 主な機能

- **🎵 Spotify 統合**: Spotify URL から音声ダウンロード・処理
- **🎵 ローカル処理**: MP3 ファイル直接処理
- **🤖 AI 分析**: Gemini AI による要約・構造化
- **💾 データベース**: 124 エピソード管理済み
- **🌐 Web ダッシュボード**: Streamlit 製管理画面
- **🔄 アカウント自動切り替え**: Summary.fm の月 5 回制限を自動回避（4 アカウント管理）

## ⚡ クイックスタート

### 1. 簡単実行（推奨）

```bash
# Spotify URL 処理
python scripts/run_spotify_processing.py

# ローカル MP3 処理
python scripts/run_local_processing.py

# Web インターフェース
python scripts/run_web_interface.py
```

### 2. 依存関係インストール

```bash
# 基本依存関係
pip install -r config/requirements/base.txt

# Web インターフェース用
pip install -r config/requirements/web.txt

# 開発用
pip install -r config/requirements/dev.txt
```

### 3. 設定ファイル

`config/config.yaml` を作成：

```yaml
spotify:
  client_id: 'your_spotify_client_id'
  client_secret: 'your_spotify_client_secret'
listen_notes:
  api_key: 'your_listen_notes_api_key'
gemini:
  api_key: 'your_gemini_api_key'
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
├── 🧪 tests/                # テストファイル
├── ⚙️  config/               # 設定・依存関係
├── 📊 data/                 # データファイル
└── 📖 docs/                 # ドキュメント
```

## 🚀 使用方法

### Spotify URL 処理

```python
# core/processors/spotify_processor.py で URL を編集
spotify_url = "https://open.spotify.com/episode/YOUR_EPISODE_ID"

# 実行
python scripts/run_spotify_processing.py
```

### ローカル MP3 処理

```python
# core/processors/local_processor.py でパスを編集
mp3_path = Path("data/downloads/your_audio.mp3")

# 実行
python scripts/run_local_processing.py
```

### Web ダッシュボード

```bash
python scripts/run_web_interface.py
# → http://localhost:8501
```

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

1. **入力**: Spotify URL または MP3 ファイル
2. **ダウンロード**: Listen Notes API 経由で音声取得
3. **文字起こし**: Summary.fm (Selenium) で文字起こし
4. **AI 処理**: Gemini で要約・構造化
5. **保存**: SQLite + Markdown ファイル出力

### アーキテクチャ

- **コア**: `core/processors/` - メイン処理ロジック
- **統合**: `integrations/` - Spotify, Listen Notes, AI APIs
- **データ**: `database/` - SQLite データベース管理
- **UI**: `web/streamlit/` - Streamlit ダッシュボード

## 📈 現在の状況

✅ **124 エピソード**登録済み  
✅ **520 セクション**解析済み  
✅ **2020 年〜2025 年**の範囲  
✅ **日英対応**完了

## 📖 詳細ドキュメント

- [📋 セットアップガイド](docs/setup/)
- [🎯 使用方法ガイド](docs/guides/)
- [⚙️ 開発者向け](docs/development/)
- [🌐 Web インターフェース](docs/guides/README_WEB_INTERFACE.md)
- [🔄 アカウント自動切り替え](docs/ACCOUNT_AUTO_SWITCH.md) - Summary.fm の月 5 回制限回避機能
- [📊 アカウント管理](docs/ACCOUNT_MANAGEMENT.md) - アカウント管理システムの詳細

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

**作成**: 2024 年 12 月 | **更新**: 2024 年 12 月 | **バージョン**: 2.0.0
