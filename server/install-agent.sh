#!/usr/bin/env bash
#
# ジョブサーバをログイン時に自動起動するよう登録する。
#
#   bash server/install-agent.sh            # 登録（既存があれば入れ替え）
#   bash server/install-agent.sh --uninstall # 解除
#
# plist のパスをこのリポジトリの実際の位置から組み立てるので、
# チェックアウト場所が変わっても壊れない。
set -euo pipefail

LABEL="com.iorikawano.podcast-notes-remote"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
# 既定はこのスクリプトが置かれているリポジトリ。検証時は環境変数で差し替えられる。
PROJECT_DIR="${PODCAST_NOTES_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON="/usr/bin/python3"

DOMAIN="gui/$(id -u)"

is_loaded() {
  # `launchctl list | grep -q` は使わない。grep -q が一致時に即終了して
  # launchctl が SIGPIPE で落ち、pipefail がそれを失敗と見なしてしまう。
  launchctl print "$DOMAIN/$LABEL" > /dev/null 2>&1
}

stop_agent() {
  if ! is_loaded; then
    return 0
  fi
  # bootout が本筋。古い macOS 向けに unload も試す。
  launchctl bootout "$DOMAIN/$LABEL" > /dev/null 2>&1 \
    || launchctl unload "$PLIST" > /dev/null 2>&1 \
    || true
  for _ in 1 2 3 4 5; do
    is_loaded || break
    sleep 1
  done
  if is_loaded; then
    echo "❌ 既存のエージェントを停止できませんでした。" >&2
    echo "   手動で: launchctl bootout $DOMAIN/$LABEL" >&2
    exit 1
  fi
  echo "既存のエージェントを停止しました"
}

if [ "${1:-}" = "--uninstall" ]; then
  # 先に停止する。plist を消してから停止しようとすると、
  # unload の対象ファイルが無くなりジョブが登録されたまま孤立する。
  stop_agent
  rm -f "$PLIST"
  echo "✅ 解除しました"
  exit 0
fi

# --- 前提の確認 -----------------------------------------------------------

if [ ! -f "$PROJECT_DIR/server/app.py" ]; then
  echo "❌ $PROJECT_DIR/server/app.py がありません" >&2
  exit 1
fi

if ! grep -q "^remote:" "$PROJECT_DIR/config/config.yaml" 2>/dev/null; then
  echo "❌ config/config.yaml に remote: セクションがありません。" >&2
  echo "   docs/REMOTE_APP.md の「1-1. トークンを決める」を先に。" >&2
  exit 1
fi

PORT="$("$PYTHON" - "$PROJECT_DIR" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1], "config", "config.yaml").read_text(encoding="utf-8")
section = re.search(r"^remote:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
match = re.search(r"port:\s*(\d+)", section.group(1) if section else "")
print(match.group(1) if match else "8765")
PY
)"

# --- 手動起動していたものを止める（ポートの二重確保を防ぐ） ----------------

stop_agent
if pgrep -f "server/app.py" > /dev/null; then
  pkill -f "server/app.py" || true
  sleep 1
  echo "手動起動していたサーバを停止しました"
fi

# --- plist を書き出して登録 -----------------------------------------------

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- server/install-agent.sh が生成。手で編集せず、スクリプトを再実行すること。 -->
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>$PYTHON</string>
		<string>$PROJECT_DIR/server/app.py</string>
	</array>
	<key>WorkingDirectory</key>
	<string>$PROJECT_DIR</string>
	<key>EnvironmentVariables</key>
	<dict>
		<!-- claude / ffmpeg などを PATH から見つけられるようにする -->
		<key>PATH</key>
		<string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
		<!-- config やパイプラインを探す場所を明示する -->
		<key>PODCAST_NOTES_PROJECT_DIR</key>
		<string>$PROJECT_DIR</string>
	</dict>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>StandardOutPath</key>
	<string>$PROJECT_DIR/logs/remote-server.log</string>
	<key>StandardErrorPath</key>
	<string>$PROJECT_DIR/logs/remote-server.err.log</string>
</dict>
</plist>
PLIST_EOF

# bootstrap が本筋。古い macOS 向けに load も試す。
launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

# --- 起動確認 -------------------------------------------------------------

for _ in $(seq 1 10); do
  if curl -fsS "http://127.0.0.1:$PORT/v1/health" > /dev/null 2>&1; then
    echo "✅ 登録して起動しました: http://127.0.0.1:$PORT"
    echo "   アプリに設定を流し込むリンク: $PYTHON server/app.py --setup-link"
    exit 0
  fi
  sleep 1
done

echo "⚠️  登録はしたものの health が返りません。ログを確認してください:" >&2
echo "   tail -20 $PROJECT_DIR/logs/remote-server.err.log" >&2
exit 1
