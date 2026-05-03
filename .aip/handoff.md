# Handoff Notes

Last updated: 2026-05-03

## What I Was Working On

原研哉氏のポッドキャスト「低空飛行 / Talk with: 牧大介（エーゼログループ代表）」前後編2エピソードの処理と、Notionページへのトピック・インデックス＋解説の追記。

## Progress Made

### 1. エピソード処理（process_unified.py）
- 前編 `44iZec5WYwfA1jLlZIn6o0` → Listen Notes ヒット → Whisper(medium) 文字起こし → Notion登録
  - Title: あるべき未来を取り戻す 前編｜Talk with : 牧大介（エーゼログループ 代表）
  - Duration: 34:06 / 文字数 10,364 / Category: Biology & Nature
  - Notion: https://www.notion.so/Talk-with-355264826e0c81ad848dcbea91d03e2e
- 後編 `1umxnSmroXN9mBGBEf8lZw` → 同上フローで成功
  - Title: あるべき未来を取り戻す 後編｜Talk with : 牧大介（エーゼログループ 代表）
  - Duration: 41:40 / 文字数 12,663 / Category: Business
  - Notion: https://www.notion.so/Talk-with-355264826e0c81aaab47c077819f05c0

### 2. トピック・インデックス＋解説のNotion追記
- 両エピソードのトランスクリプトから話題を網羅抽出 → 一般リサーチで裏取り → md記法で索引＋解説を作成
- リサーチ範囲：人物（牧大介、原研哉、山極壽一、高橋勇夫など）、組織（エーゼログループ、森の学校、アミタ、BASE 101%、のきした図書館）、場所（西粟倉村、マリアナ諸島、瀬戸田、知床）、思想・施策（百年の森林構想、列状/劣勢木間伐、6次産業化、会社の百姓化、ビオ田んぼ、ポータブル魚道、奥の院ゾーニング、ライフヒストリーのアーカイブ）、生き物（ニホンウナギ、タガメ、オオサンショウウオ、シロサケ、モクズガニ、アユ、ヌマエビ、カワエビ等）、文化論（縄文、ごちそう語源、縦割り行政）
- 出力: `data/outputs/<タイトル>/index_supplement.md`（前編・後編それぞれ）
- 追記スクリプト: `append_index_to_notion.py`（プロジェクトルートに新規作成）
  - md→Notionブロック変換器を実装：##/###/####（boldパラグラフ）/段落/箇条書き/quote/divider、インラインで `[text](url)` / `**bold**` / `*italic*` に対応
  - 各ページに前編75ブロック、後編79ブロック追記成功

### 3. リサーチで判明した本編の表記訂正
- 「山際順次」→ **山極壽一**（やまぎわ じゅいち）京大元総長・現総合地球環境学研究所所長
- 「野木下図書館」→ **のきした図書館**（古民家B&B、児童文庫併設）
- 「神奈川厚生の高橋先生」→ 神奈川工科大の可能性ありとして注記。一次ソース未確定

## Next Steps

1. 高橋勇夫氏とポータブル魚道開発の関係について一次ソース確認（必要なら本編再聴取）
2. 前編・後編のトランスクリプト冒頭の繰り返し誤認識（Whisper の "大学に行って..." 循環など）の手当て検討
3. `process_unified.py` 等の未コミット変更（git status上にM/??が大量）の整理・コミット方針を確認

## Blockers / Questions

- `notion_snapshot.md` はPlaywrightのアクセシビリティスナップショットで、ステータス用途ではない（混在しているので別場所に切り出すか要判断）
- 大量の未追跡スクリプト（`append_index_to_notion.py`, `update_notion_page.py`, `batch_update_episodes.py`, `fix_notion_transcript_format.py` 等）が既にあり、整理が必要

## Notes for Next Session

- Notion DB は `config/config.yaml` に設定済み。各エピソードページIDの対応：
  - 前編: `355264826e0c81ad848dcbea91d03e2e`
  - 後編: `355264826e0c81aaab47c077819f05c0`
- `append_index_to_notion.py` は既存ページ末尾にmdを追記する汎用ツールとして再利用可能。`TASKS` 配列を編集すれば他エピソードでも使える
- Whisperは medium モデル、CPU・FP32で1本7〜8分（30〜40分尺の場合）
