#!/usr/bin/env python3
"""Podcast Notes remote job server の HTTP 層。

    python3 server/app.py

iPhone アプリ（ios/PodcastNotesRemote）から叩かれる JSON API。
標準ライブラリのみ。Bearer トークン必須。

エンドポイント:
    GET  /v1/health
    POST /v1/jobs              {kind, spotify_url?, prompt?, language?, llm_backend?, ...}
    GET  /v1/jobs?limit=50
    GET  /v1/jobs/{id}
    GET  /v1/jobs/{id}/log?offset=0
    POST /v1/jobs/{id}/cancel

    python3 server/app.py --setup-link   # アプリに設定を流し込む URL を表示
"""

from __future__ import annotations

import argparse
import hmac
import json
import re
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs, quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_server import (  # noqa: E402
    SPOTIFY_EPISODE_RE,
    JobStore,
    Settings,
    Worker,
)

MAX_BODY_BYTES = 256 * 1024
MAX_PROMPT_CHARS = 8000

JOB_PATH_RE = re.compile(r"^/v1/jobs/([0-9a-f]{6,32})$")
JOB_LOG_PATH_RE = re.compile(r"^/v1/jobs/([0-9a-f]{6,32})/log$")
JOB_CANCEL_PATH_RE = re.compile(r"^/v1/jobs/([0-9a-f]{6,32})/cancel$")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "PodcastNotesRemote/1.0"
    protocol_version = "HTTP/1.1"

    settings: Settings
    store: JobStore
    worker: Worker

    # -- 共通 -------------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self) -> None:
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(token, self.settings.token):
            raise ApiError(401, "トークンが正しくありません")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Content-Length が不正です")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "リクエストが大きすぎます")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(400, f"JSON を解釈できません: {exc}")

    # -- ルーティング -----------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path, query = parsed.path.rstrip("/") or "/", parse_qs(parsed.query)
        try:
            if method == "GET" and path == "/v1/health":
                self._send_json(200, {"ok": True, "version": self.server_version})
                return

            self._authorize()

            if method == "POST" and path == "/v1/jobs":
                self._send_json(201, self._create_job(self._read_json()))
                return
            if method == "GET" and path == "/v1/jobs":
                limit = self._int_param(query, "limit", default=50, lo=1, hi=200)
                self._send_json(200, {"jobs": self.store.list(limit)})
                return

            if m := JOB_PATH_RE.match(path):
                if method != "GET":
                    raise ApiError(405, "許可されていないメソッドです")
                self._send_json(200, self._require_job(m.group(1)))
                return
            if m := JOB_LOG_PATH_RE.match(path):
                if method != "GET":
                    raise ApiError(405, "許可されていないメソッドです")
                self._send_json(200, self._job_log(m.group(1), query))
                return
            if m := JOB_CANCEL_PATH_RE.match(path):
                if method != "POST":
                    raise ApiError(405, "許可されていないメソッドです")
                job_id = m.group(1)
                self._require_job(job_id)
                cancelled = self.worker.cancel(job_id)
                self._send_json(200, {"cancelled": cancelled, "job": self.store.get(job_id)})
                return

            raise ApiError(404, "そのエンドポイントはありません")
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except Exception as exc:  # 予期しない例外でも接続を閉じない
            self.log_message("unhandled error: %r", exc)
            self._send_json(500, {"error": f"サーバ内部エラー: {exc}"})

    # -- ハンドラ ---------------------------------------------------------

    def _require_job(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job is None:
            raise ApiError(404, "ジョブが見つかりません")
        return job

    @staticmethod
    def _int_param(query: dict, name: str, default: int, lo: int, hi: int) -> int:
        raw = (query.get(name) or [None])[0]
        if raw is None:
            return default
        try:
            return max(lo, min(hi, int(raw)))
        except ValueError:
            raise ApiError(400, f"{name} は整数で指定してください")

    def _create_job(self, body: dict) -> dict:
        kind = (body.get("kind") or "").strip() or None
        spotify_url = (body.get("spotify_url") or "").strip()
        prompt = (body.get("prompt") or "").strip()

        # kind 省略時は入力から推測する（アプリ側を単純に保つため）
        if kind is None:
            kind = "episode" if spotify_url else "ask"
        if kind not in ("episode", "ask"):
            raise ApiError(400, "kind は episode か ask です")

        if spotify_url:
            match = SPOTIFY_EPISODE_RE.search(spotify_url)
            if not match:
                raise ApiError(400, "Spotify のエピソード URL ではありません")
            spotify_url = match.group(0)
        elif kind == "episode":
            raise ApiError(400, "spotify_url が必要です")

        if kind == "ask" and not prompt:
            raise ApiError(400, "依頼内容（prompt）が空です")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise ApiError(400, f"依頼内容が長すぎます（最大 {MAX_PROMPT_CHARS} 文字）")

        language = body.get("language") or None
        if language not in (None, "ja", "en"):
            raise ApiError(400, "language は ja か en です")
        llm_backend = body.get("llm_backend") or None
        if llm_backend not in (None, "gemini", "lmstudio"):
            raise ApiError(400, "llm_backend は gemini か lmstudio です")

        job = self.store.create(
            kind=kind,
            title=(body.get("title") or "").strip() or None,
            spotify_url=spotify_url or None,
            prompt=prompt or None,
            language=language,
            llm_backend=llm_backend,
            no_verify=bool(body.get("no_verify")),
            no_notion=bool(body.get("no_notion")),
        )
        self.worker.submit(job["id"])
        return job

    def _job_log(self, job_id: str, query: dict) -> dict:
        self._require_job(job_id)
        offset = self._int_param(query, "offset", default=0, lo=0, hi=1 << 31)
        path = self.store.log_path(job_id)
        if not path.exists():
            return {"offset": 0, "next_offset": 0, "chunk": ""}
        data = path.read_bytes()
        # ログが切り詰められた／別ジョブを跨いだ場合は先頭に巻き戻す
        if offset > len(data):
            offset = 0
        chunk = data[offset : offset + 64 * 1024]
        return {
            "offset": offset,
            "next_offset": offset + len(chunk),
            "chunk": chunk.decode("utf-8", errors="replace"),
        }


def lan_address() -> Optional[str]:
    """同一 LAN から見える自分の IP。取れなければ None。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))  # 実際には送信しない
            return sock.getsockname()[0]
    except OSError:
        return None


def tailscale_hostname() -> Optional[str]:
    """Tailscale 上の自分の DNS 名。未導入なら None。"""
    try:
        output = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        status = json.loads(output)
        name = (status.get("Self") or {}).get("DNSName") or ""
        return name.rstrip(".") or None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError):
        return None


def print_setup_links(settings: Settings) -> int:
    """アプリに接続設定を流し込む URL を表示する。

    43 文字のトークンを iPhone のキーボードで打たせないためのもの。
    """
    if not settings.token:
        print("❌ config/config.yaml の remote.token が未設定です", file=sys.stderr)
        return 1

    hosts: list[tuple[str, str]] = []
    if name := tailscale_hostname():
        hosts.append(("外出先からも使える (Tailscale)", f"{name}:{settings.port}"))
    if ip := lan_address():
        hosts.append(("自宅の Wi-Fi 内のみ", f"{ip}:{settings.port}"))
    if not hosts:
        print("❌ 自分のアドレスを特定できませんでした", file=sys.stderr)
        return 1

    print("iPhone の Safari で開くか、メモ／メッセージ経由で自分に送って開いてください。\n")
    for label, host in hosts:
        link = (
            f"podcastnotes://configure"
            f"?server={quote(host, safe='')}&token={quote(settings.token, safe='')}"
        )
        print(f"■ {label}")
        print(f"  {link}\n")
    print("※ このリンクにはトークンが入っています。他人に共有しないでください。")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Podcast Notes remote job server")
    parser.add_argument(
        "--setup-link",
        action="store_true",
        help="iPhone アプリに接続設定を流し込む URL を表示して終了する",
    )
    args = parser.parse_args(argv)

    settings = Settings()

    if args.setup_link:
        return print_setup_links(settings)

    if not settings.project_dir.exists():
        print(f"❌ プロジェクトディレクトリがありません: {settings.project_dir}", file=sys.stderr)
        return 1
    if not settings.token:
        print(
            "❌ トークンが設定されていません。\n"
            "   config/config.yaml に次を追記してください:\n\n"
            "   remote:\n"
            "     token: '<十分に長いランダム文字列>'\n\n"
            "   生成例: python3 -c \"import secrets;print(secrets.token_urlsafe(32))\"",
            file=sys.stderr,
        )
        return 1
    if len(settings.token) < 16:
        print("❌ トークンが短すぎます（16 文字以上にしてください）", file=sys.stderr)
        return 1

    store = JobStore(settings.state_dir)
    worker = Worker(settings, store)
    worker.start()

    Handler.settings = settings
    Handler.store = store
    Handler.worker = worker

    httpd = ThreadingHTTPServer((settings.host, settings.port), Handler)
    print(f"🎧 podcast-notes remote server: http://{settings.host}:{settings.port}")
    print(f"   project_dir : {settings.project_dir}")
    print(f"   python      : {settings.python}")
    print(f"   claude      : {settings.claude_bin} (--permission-mode {settings.claude_permission_mode})")
    print(f"   state       : {settings.state_dir}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
