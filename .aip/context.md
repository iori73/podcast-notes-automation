# Project Context: Podcast Notes Automation

Created: 2026-01-21
Last updated: 2026-05-03

## Overview

Spotify URL や MP3 ファイルからポッドキャストを自動で文字起こし・要約・構造化ノート生成し、Notion DB に登録するシステム。バージョン3.1.0系。

## Tech Stack

- Python 3.14（`.venv/` 配下に仮想環境）
- 文字起こし: OpenAI Whisper（ローカル, mediumモデル, CPU・FP32）
- 音声検索: Listen Notes API → 失敗時 iTunes Search API + RSS フォールバック → 失敗時 Spotify HTML（Browser MCP）
- 要約・チャプター生成: Claude（対話的）
- データ永続化: Notion API（`https://api.notion.com/v1/...`）
- 設定: `config/config.yaml`（API キー類）

## Key Files

- `process_unified.py` — 統合処理エントリ（推奨）
- `process_spotify_transcript.py` — Spotify HTML から処理
- `local_transcriber/process.py` — ローカル音声から処理
- `src/listen_notes.py` — Listen Notes 検索
- `src/integrations/itunes_rss.py` — iTunes/RSS フォールバック
- `src/integrations/notion_client.py` — Notion ブロック変換 & DB 登録（Transcript はトグル化、100ブロック制限を自動分割）
- `local_transcriber/transcriber.py` — Whisper ラッパー
- `append_index_to_notion.py` — 既存Notionページの末尾に md を追記する汎用ツール（2026-05-03 追加）
- `data/outputs/<title>/episode_summary.md` — 各エピソードの要約MD
- `data/outputs/<title>/index_supplement.md` — トピック・インデックス＋解説MD（必要時に作成）

## Conventions

- 出力ファイル名は Spotify エピソードタイトル（「：」「/」など一部記号は変換）
- Notion DB プロパティ: Name / URL / Podcast / Release Date / 1. Duration / Category
- Transcript は Notion 上でトグルブロックに格納（children上限100超は別途追加）
- 言語デフォルト: ja

## Current State

- 直近2エピソード（牧大介氏前後編）は処理済み・Notion登録＋索引追記まで完了
- 前編 page_id: `355264826e0c81ad848dcbea91d03e2e`
- 後編 page_id: `355264826e0c81aaab47c077819f05c0`
- 未コミットの追加スクリプトが多数あり（`append_index_to_notion.py`, `update_notion_page.py`, `batch_update_episodes.py`, `fix_notion_transcript_format.py` 等）
- README/コア処理にもM変更が複数あり、コミット方針の整理が必要
