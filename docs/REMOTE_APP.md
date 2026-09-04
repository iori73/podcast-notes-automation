# スマホから Podcast Notes を動かす

パソコンの前にいなくても、iPhone から Spotify の URL を投げるだけで
今までと同じフォーマットの Notion ページが出来上がるようにする仕組み。

追加の依頼（例:「この回で話されているすべての文様や家紋について、
ビジュアルのリファレンス画像を Notion のページに入れて」）も同じ画面から投げられる。

---

## 全体像

```
iPhone アプリ                   Mac（自宅で起動しっぱなし）
┌────────────────┐             ┌──────────────────────────────────┐
│ Spotify URL    │  HTTP/JSON  │ server/app.py（ジョブサーバ）     │
│ ＋ 追加の依頼   │ ──────────▶ │   ↓ 1 本ずつ直列に実行            │
│                │             │ ① process_unified.py → Notion    │
│ 履歴・状態・ログ │ ◀────────── │ ② claude -p で追加の依頼を実行    │
└────────────────┘             └──────────────────────────────────┘
```

重い処理（Whisper の文字起こし、要約、Notion 書き込み）は全部 Mac 側。
iPhone 側は依頼を出して結果を見るだけなので、アプリを閉じても処理は続く。

**3 つの使い方**

| 入力 | 動くもの |
| --- | --- |
| URL だけ | 今までどおりのノート生成 |
| URL ＋ 追加の依頼 | ノート生成 → 続けて追加の依頼を実行 |
| 追加の依頼だけ | 既存ページなどへの自由な依頼を Claude Code が実行 |

---

## 1. Mac 側のセットアップ

### 1-1. トークンを決める

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`config/config.yaml` の末尾に追記する（このファイルは Git 管理外）。

```yaml
remote:
  token: '<上で出た文字列>'
  host: '0.0.0.0'
  port: 8765
  # 無人実行のため、許可プロンプトを出さない設定にしている。
  # 自分の Mac 上でトークン保護された状態で使うことが前提。
  claude_permission_mode: 'bypassPermissions'
```

設定できる項目:

| キー | 既定値 | 説明 |
| --- | --- | --- |
| `token` | （必須） | iPhone アプリと共有する合言葉。16 文字以上 |
| `host` | `0.0.0.0` | 待ち受けアドレス |
| `port` | `8765` | 待ち受けポート |
| `python` | `venv/bin/python` | パイプラインを動かす Python |
| `claude_bin` | `claude` | Claude Code の実行ファイル |
| `claude_permission_mode` | `bypassPermissions` | 追加依頼の実行時の許可モード |
| `episode_timeout` | `7200` | ノート生成の上限秒数 |
| `ask_timeout` | `3600` | 追加依頼の上限秒数 |

### 1-2. 起動

```bash
python3 server/app.py
```

追加インストールは不要（標準ライブラリのみ）。動作確認:

```bash
curl http://localhost:8765/v1/health
# → {"ok": true, "version": "PodcastNotesRemote/1.0"}
```

### 1-3. ログイン時に自動起動する

```bash
cp server/com.iorikawano.podcast-notes-remote.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.iorikawano.podcast-notes-remote.plist
```

ログは `logs/remote-server.log` に出る。

### 1-4. Mac をスリープさせない

スリープ中はジョブが進まない（キューに残り、復帰後に動く）。
外出中も使うなら「システム設定 → ロック画面 → ディスプレイがオフのときは自動でスリープさせない」を有効に。

---

## 2. 外出先から Mac に届かせる

### 自宅の Wi-Fi だけで使う場合

Mac の IP をアプリに入れるだけ。

```bash
ipconfig getifaddr en0    # 例: 192.168.1.10
```

→ アプリの設定に `192.168.1.10:8765`

### 外出先からも使う場合（推奨: Tailscale）

ポート開放をせずに、iPhone と Mac を同じ仮想ネットワークに入れる。

1. Mac と iPhone の両方に [Tailscale](https://tailscale.com) を入れて同じアカウントでログイン
2. Mac の名前を確認: `tailscale status`（例: `iori-mac.tail1234.ts.net`）
3. アプリの設定に `iori-mac.tail1234.ts.net:8765`

> ルータのポート開放でインターネットに直接晒すのは避けること。
> このサーバは Claude Code を許可プロンプトなしで動かせるため、
> 到達できる範囲は最小限にしておく。

---

## 3. iPhone アプリのインストール

```bash
cd ios
xcodegen generate
open PodcastNotesRemote.xcodeproj
```

Xcode で iPhone を繋いで Run。無料の Apple ID でも実機に入る（7 日ごとに再ビルドが必要）。

> `xcodebuild` が `command line tools instance` エラーになる場合:
> `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
> （一時的に回避するなら `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild ...`）

### 初回設定（トークンを手打ちしない）

43 文字のトークンを iPhone のキーボードで打つのは辛いので、設定を流し込む URL を出せる。

```bash
python3 server/app.py --setup-link
```

Tailscale が入っていればその名前、入っていなければ LAN の IP を使ったリンクが出る。
iPhone の Safari で開く（メモやメッセージ経由で自分に送ってタップでもよい）と、
「Open in "Podcast Notes"?」→ Open で設定が入る。

手で入れる場合は「設定」タブに URL とトークンを入力。
どちらの場合も最後に「接続を確認」を押して ✅ になることを確かめる。

> リンクにはトークンが平文で入る。人に共有しないこと。

---

## 4. 共有シートから投げる（iOS ショートカット）

Spotify アプリの共有シートから直接投げたい場合は、ショートカットを 1 つ作る。
（アプリ本体の Share Extension は App Group の証明書が要るため、こちらを推奨）

1. ショートカット App →「＋」→ 名前を「ポッドキャストをノート化」に
2. 「詳細」→「共有シートに表示」をオン、受け取る種類を **URL** のみに
3. アクション「**URL の内容を取得**」を追加し、次のように設定
   - URL: `http://<Mac のアドレス>:8765/v1/jobs`
   - 方法: `POST`
   - ヘッダ: `Authorization` = `Bearer <トークン>`
   - 本文を要求: `JSON`
     - `spotify_url` （テキスト）→ **ショートカットの入力**
     - `prompt` （テキスト）→ 空、または毎回聞きたいなら「入力を要求」

これで Spotify の共有シートから 2 タップで投げられる。
状況の確認はアプリの「履歴」タブで。

### URL スキーム

| URL | 動作 |
| --- | --- |
| `podcastnotes://submit?url=<Spotify URL>` | アプリを開いて URL 欄に入れた状態にする |
| `podcastnotes://configure?server=<host:port>&token=<token>` | 接続設定を流し込む（`--setup-link` が出すもの） |

値は URL エンコードして渡す。

---

## 5. API リファレンス

すべて `Authorization: Bearer <token>` が必要（`/v1/health` を除く）。

| メソッド | パス | 説明 |
| --- | --- | --- |
| `GET` | `/v1/health` | 疎通確認（認証不要） |
| `POST` | `/v1/jobs` | ジョブ投入 |
| `GET` | `/v1/jobs?limit=50` | 履歴一覧 |
| `GET` | `/v1/jobs/{id}` | 1 件の状態 |
| `GET` | `/v1/jobs/{id}/log?offset=0` | 実行ログの続きを取得 |
| `POST` | `/v1/jobs/{id}/cancel` | 中止（プロセスツリーごと停止） |

### ジョブ投入の本文

```jsonc
{
  "spotify_url": "https://open.spotify.com/episode/xxx",  // ある → ノート生成
  "prompt": "この回の文様や家紋の画像を Notion に入れて",      // ある → 追加依頼
  "title": "#63 家紋の世界",                                // 任意。履歴の見出し
  "language": "ja",         // ja | en。省略で自動判定
  "llm_backend": "gemini",  // gemini | lmstudio。省略でサーバ既定
  "no_verify": false,
  "no_notion": false
}
```

`kind` は省略できる。`spotify_url` があれば `episode`、無ければ `ask` になる。

### コマンドラインから投げる例

```bash
curl -X POST http://localhost:8765/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "spotify_url": "https://open.spotify.com/episode/xxx",
        "prompt": "この回で話されているすべての文様や家紋について、ビジュアルのリファレンス画像を Notion のページに入れて"
      }'
```

---

## 6. 仕様と制約

- **直列実行**: Whisper と LLM を同時に走らせるとメモリを食い潰すため、ジョブは常に 1 本ずつ。
- **状態の保存先**: `data/remote_jobs/jobs.json` と `data/remote_jobs/<job_id>.log`。最新 200 件を保持。
- **サーバ再起動**: 実行中だったジョブは「サーバ再起動により中断されました」として失敗扱いになる。投げ直しが必要。
- **プッシュ通知は無し**: 完了通知は送られない。アプリを開いている間だけ 5 秒間隔で状態を見に行く。
- **Gemini の無料枠**: 1 日あたりモデルごと 20 リクエスト。1 エピソードで約 6 コール消費するので、枯渇したら翌日か LM Studio に切り替える。
- **追加依頼は Claude Code 任せ**: 何ができるかは Claude Code の権限（Notion MCP、リポジトリ内のスクリプト等）と同じ。結果はジョブのログで確認する。
