# 運用状況（最終更新: 2026-10-10）

他セッション・他の人が最新状況から話を始めるための記録。コードの構造ではなく「今どうなっているか」だけを書く。

## Notion データベース
- **Podcast Notes Database は 2026-10-10 に workspace の root（Private）へ手動で移動済み**。以前は「副業 / STUDIO作成？ / STUDIOの実績作り『Podcast Notes』」配下だった。
- 移動で親ページ経由の共有が切れたため、DB に接続 `Podcast Notes Database ⁕ 20251218` を手動で追加した。追加後、パイプラインの API 経由で DB 取得・クエリが通ることを確認済み（DB IDは移動前後で変わらず、`config/config.yaml` の `notion.database_id` のまま）。
- 注意: Notion の公開 APIには「workspace rootへ移動」も「接続の追加」もない。どちらもUI操作が必要。DBを動かし直した時は、移動後に接続が外れていないか必ず確認する（外れると `Could not find database ... shared with your integration` で404になる）。
- Claude Code の Notion MCP（plugin:Notion）は、パイプラインのインテグレーションとは別接続。同じDBは見えない。DBの存在確認はパイプラインの `api_key` で行う。

## 処理済みエピソード（直近）
| 日付 | エピソード | Notion |
|---|---|---|
| 2026-10-10 | 佐渡島庸平の好きのおすそ分け #67「アドバイスの罠」 | https://app.notion.com/p/67-3f5264826e0c8102a02cca225a43adae |
| 2026-10-10 | 佐渡島庸平の好きのおすそ分け #90 山内朋樹さん「放っておく」 | https://app.notion.com/p/90-3f5264826e0c81e0a977fe8501ab1573 |

両方とも Listen Notes / iTunes に見つからず、Spotify の Transcript タブをブラウザで取得して `--html-file` で処理した（ソース: `spotify_html`）。

## Spotify Transcript をブラウザで取得する手順（自動取得が両方失敗した時）
1. chrome-devtools MCP で Spotify のエピソードURLを開く（自動化用Chromeにログイン済みセッションが残っている）。
2. `[role="tab"]` の "Transcript" をクリック。
3. 本文は `#transcript-panel` 内の子要素が多いdiv（タイムスタンプの `button` 行 → 本文の `div` 行）。リストは仮想化されているので、スクロールと収集を**1回の `evaluate_script` 内**で行う。
4. 収集結果は `evaluate_script` の `filePath` でプロジェクト配下にJSON保存（プロジェクト外は不可）。
5. `<button><span>ts</span></button><p>text</p>` のHTMLに組み直し、`python process_unified.py "<URL>" --html-file <file>` に渡す。日本語の字間スペースはパイプライン側で整形される。

## コードの状態
`process_unified.py`・`src/philosophy.py`・`src/verification.py`・`bin/podcast-notes`・`requirements.txt` などの作業は PR #3 で origin/main にマージ済み。`config/config.yaml`（APIキー・DB ID）は .gitignore で管理外。
