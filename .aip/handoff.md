# Handoff Notes

Last updated: 2026-08-11

## What I Was Working On

LM Studio（ローカルLLM）移行の本番統合。検証フェーズは完了済み。`process_unified.py` に A（6チャンク間引き修正）→ B（バックエンド切替）を入れた。

## Progress Made

### A. 6チャンク間引きバグ修正（完了）
- `_generate_summary_and_timestamps` の `chunks[:2] + mid + [-2:]` 間引きを**削除**
- 長尺回で中盤（固有名詞含む）が要約対象から落ちる既存バグを解消（Gemini運用にも効く）

### B. LM Studio バックエンド統合（完了）
- `--llm-backend {gemini,lmstudio}`（デフォルト `gemini`。`config.yaml` の `llm.backend` でも可）
- `_lmstudio_generate` / `_llm_generate` ディスパッチ
- 検証済み3点を本体へ移植:
  1. Markdown装飾耐性の Summary / Key Takeaways 分割正規表現
  2. 最終まとめ `temperature=0.3` + LaTeX禁止指示
  3. 固有名詞保持指示
- `config/config.yaml` に `llm` / `lmstudio` セクション追加（gitignore対象）
- README に使い方追記
- LM Studio 起動確認済み（`google/gemma-4-e4b` @ localhost:1234、context 要確認）

## Next Steps

1. **実運用スモーク**: 既存文字起こしがある1〜2本を `--llm-backend lmstudio --no-notion` で流し、人力チェック
2. 英語回・長尺回は当面 Gemini と並行比較して抜けがないか確認
3. 問題なければ `llm.backend: lmstudio` をデフォルト候補に検討
4. 未コミット変更の整理・コミット方針確認（ユーザー依頼時のみ）

## Blockers / Questions

- LM Studio の context-length はロード時に明示（`lms load ... --context-length 16384`）。4096だと空応答
- 1回しか出ない固有名詞の最終集約漏れは残存リスク（プロンプト改善で緩和済み、ゼロではない）

## Notes for Next Session

```bash
# ローカルLLMで要約のみ（Notionなし）
python process_unified.py "<spotify_url>" --llm-backend lmstudio --no-notion

# 従来どおり Gemini（デフォルト）
python process_unified.py "<spotify_url>" --no-notion
```

検証スクリプト: `scripts/test_lmstudio_quality.py`  
メモリ: `~/.claude/projects/.../memory/project_lmstudio_migration_eval.md`
