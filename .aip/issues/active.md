# Active Issues

現在取り組み中のタスク・課題

## Format

```
- [ ] [優先度] タスク内容 (#issue-id)
      - 進捗メモ
```

---

<!-- アクティブなタスクをここに追記 -->

- [x] [高] 牧大介氏 前後編エピソードを Notion 登録 (#maki-2ep)
      - 2026-05-03 完了。前編 https://www.notion.so/Talk-with-355264826e0c81ad848dcbea91d03e2e / 後編 https://www.notion.so/Talk-with-355264826e0c81aaab47c077819f05c0
- [x] [高] 牧大介氏 前後編に網羅的トピック・インデックス＋解説を Notion 追記 (#maki-2ep-index)
      - 2026-05-03 完了。`append_index_to_notion.py` 経由で前編75/後編79ブロックを末尾追記
- [-] [中] 高橋勇夫氏とポータブル魚道開発の関係について一次ソース確認 (#takahashi-fishway)
      - 2026-05-03 追加リサーチ実施。Web検索のスニペット範囲では確定ソースなし。
        - 神奈川工科大の高橋姓研究者は照明・視覚分野の高橋宏氏のみで、河川/魚道分野には不在
        - 高橋勇夫氏（たかはし河川生物調査事務所）は天然アユ研究の第一人者だが「ポータブル魚道開発者」と明言する一次ソースは未取得
        - エーゼログループ公式に「ポータブル魚道」設置や神奈川工科大連携の言及なし
      - **仮説**: 「神奈川工科大」は **「高知大学」「高知工科大」** の聞き違い、ヒトは高橋勇夫氏で整合的。
      - 残作業: WebFetchが許可される環境で hito-ayu.net 業績目録PDF / J-STAGE / J-PlatPat を精査するか、本編音声を再聴取して正確な所属名を確認
- [x] [中] 大量の未コミット変更/未追跡スクリプトのコミット方針整理 (#repo-cleanup)
      - 2026-05-03 完了。ワーキングツリーはクリーン。6コミットに分割：
        1. `f58d0b2` chore(gitignore): exclude personal/runtime/debug artifacts
        2. `c77ae53` feat: v3.1.0 unified processor with iTunes/RSS fallback and Notion improvements
        3. `a893d43` fix(whisper): suppress hallucination loops in transcription
        4. `5bbfb77` chore(summary_fm): minor cleanup
        5. `bf4de0a` feat(scripts): Notion utility scripts for index/update/batch/fix
        6. `c8393c2` chore(project): add .aip session tracking and .cursorrules
      - 物理削除は許可されなかったので PNG/snapshot は `.gitignore` で除外（ファイルはディスクに残置）
- [x] [低] Whisper トランスクリプト冒頭の循環誤認識（"大学に行って..." の繰り返し等）の手当て検討 (#whisper-loop)
      - 2026-05-03 適用。`local_transcriber/transcriber.py` で `condition_on_previous_text=False` を中心に
        Whisperの hallucination 抑制パラメータを明示指定（compression/logprob/no-speech 閾値、温度フォールバック）。
      - 影響範囲: 同モジュールを呼ぶ全エピソード処理。次回処理から効果を検証

