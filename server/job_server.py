#!/usr/bin/env python3
"""Podcast Notes remote job server.

iPhone から Spotify URL や自由文の依頼を受け取り、Mac 上で

  * episode ジョブ: process_unified.py を実行して Notion ページを生成
  * ask ジョブ:     claude -p を headless 実行して自由な依頼を処理

を直列に捌く。標準ライブラリのみで動くので追加インストールは不要。

このファイルは設定・ジョブストア・ワーカーを持つ。HTTP 層と起動口は
server/app.py 側にあるので、サーバを動かすときは:

    python3 server/app.py

設定は config/config.yaml の remote: セクション（無ければ環境変数）。
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import signal
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# このファイルが置かれているリポジトリを既定の作業対象にする。
# 絶対パスを直書きしないので、リポジトリを移動しても壊れない。
# 別の場所を対象にしたいときは PODCAST_NOTES_PROJECT_DIR で上書きする。
DEFAULT_PROJECT_DIR = Path(__file__).resolve().parent.parent

SPOTIFY_EPISODE_RE = re.compile(
    r"https?://open\.spotify\.com/(?:[a-z-]+/)?episode/[A-Za-z0-9]+"
)
NOTION_URL_RE = re.compile(r"https://(?:www\.)?notion\.so/[^\s\"'<>）)]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# 設定
# --------------------------------------------------------------------------

def _load_yaml_remote_section(config_path: Path) -> dict:
    """config.yaml の remote: セクションだけを読む。

    PyYAML があればそれを使い、無ければ `remote:` 配下の 1 階層の
    スカラーだけを手で読む（依存ゼロで起動できるようにするため）。
    """
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        section = data.get("remote") or {}
        return section if isinstance(section, dict) else {}
    except Exception:
        pass

    section: dict[str, str] = {}
    in_remote = False
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[:1].isspace():
            in_remote = raw.split(":", 1)[0].strip() == "remote"
            continue
        if in_remote and ":" in raw:
            key, _, value = raw.strip().partition(":")
            section[key.strip()] = value.strip().strip("'\"")
    return section


class Settings:
    def __init__(self) -> None:
        self.project_dir = Path(
            os.environ.get("PODCAST_NOTES_PROJECT_DIR") or DEFAULT_PROJECT_DIR
        ).expanduser()

        remote = _load_yaml_remote_section(self.project_dir / "config" / "config.yaml")

        self.host = os.environ.get("PODCAST_NOTES_HOST") or remote.get("host") or "0.0.0.0"
        self.port = int(os.environ.get("PODCAST_NOTES_PORT") or remote.get("port") or 8765)
        self.token = os.environ.get("PODCAST_NOTES_TOKEN") or remote.get("token") or ""

        self.python = Path(
            os.environ.get("PODCAST_NOTES_PYTHON")
            or remote.get("python")
            or (self.project_dir / "venv" / "bin" / "python")
        )
        self.claude_bin = (
            os.environ.get("PODCAST_NOTES_CLAUDE") or remote.get("claude_bin") or "claude"
        )
        # headless の claude は許可プロンプトに応答できないため、無人実行するなら
        # bypassPermissions が要る。自分の Mac 上でトークン保護された運用が前提。
        self.claude_permission_mode = (
            os.environ.get("PODCAST_NOTES_CLAUDE_PERMISSION_MODE")
            or remote.get("claude_permission_mode")
            or "bypassPermissions"
        )
        self.episode_timeout = int(
            os.environ.get("PODCAST_NOTES_EPISODE_TIMEOUT")
            or remote.get("episode_timeout")
            or 7200
        )
        self.ask_timeout = int(
            os.environ.get("PODCAST_NOTES_ASK_TIMEOUT")
            or remote.get("ask_timeout")
            or 3600
        )
        self.state_dir = self.project_dir / "data" / "remote_jobs"


# --------------------------------------------------------------------------
# ジョブストア
# --------------------------------------------------------------------------

class JobStore:
    """JSON ファイルに永続化する単純なジョブストア。再起動しても履歴が残る。"""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = state_dir / "jobs.json"
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for job in data.get("jobs", []):
            # プロセスが死んだ状態で残っている実行中ジョブは中断扱いにする
            if job.get("status") in ("queued", "running"):
                job["status"] = "failed"
                job["error"] = "サーバ再起動により中断されました"
                job["finished_at"] = job.get("finished_at") or now_iso()
            self._jobs[job["id"]] = job

    def _flush_locked(self) -> None:
        jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)[:200]
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def create(self, **fields: Any) -> dict:
        with self._lock:
            job = {
                "id": uuid.uuid4().hex[:12],
                "status": "queued",
                "created_at": now_iso(),
                "started_at": None,
                "finished_at": None,
                "notion_url": None,
                "error": None,
                "result_text": None,
                **fields,
            }
            self._jobs[job["id"]] = job
            self._flush_locked()
            return dict(job)

    def update(self, job_id: str, **fields: Any) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.update(fields)
            self._flush_locked()
            return dict(job)

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
            return [dict(j) for j in jobs[:limit]]

    def log_path(self, job_id: str) -> Path:
        return self.state_dir / f"{job_id}.log"


# --------------------------------------------------------------------------
# ワーカー
# --------------------------------------------------------------------------

class Worker(threading.Thread):
    """ジョブを 1 本ずつ直列に実行する。

    Whisper と LLM が同時に複数走るとメモリを食い潰すので並列化しない。
    """

    def __init__(self, settings: Settings, store: JobStore) -> None:
        super().__init__(daemon=True, name="podcast-notes-worker")
        self.settings = settings
        self.store = store
        self.queue: queue.Queue[str] = queue.Queue()
        self._current: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    # -- 外部 API ---------------------------------------------------------

    def submit(self, job_id: str) -> None:
        self.queue.put(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            self._cancelled.add(job_id)
            proc = self._current.get(job_id)
        if proc and proc.poll() is None:
            self._kill_tree(proc, signal.SIGTERM)
            return True
        job = self.store.get(job_id)
        if job and job["status"] == "queued":
            self.store.update(
                job_id, status="cancelled", finished_at=now_iso(), error="キャンセルされました"
            )
            return True
        return False

    @staticmethod
    def _kill_tree(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    # -- 実行 -------------------------------------------------------------

    def run(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                self._run_job(job_id)
            except Exception as exc:  # ワーカーは絶対に落とさない
                self.store.update(job_id, status="failed", finished_at=now_iso(), error=repr(exc))
            finally:
                self.queue.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        with self._lock:
            already_cancelled = job_id in self._cancelled
        if already_cancelled:
            self._cancelled.discard(job_id)
            self.store.update(
                job_id, status="cancelled", finished_at=now_iso(), error="キャンセルされました"
            )
            return

        self.store.update(job_id, status="running", started_at=now_iso())
        log_path = self.store.log_path(job_id)

        if job["kind"] == "episode":
            ok = self._run_episode(job, log_path)
        else:
            ok = self._run_ask(job, log_path)

        with self._lock:
            cancelled = job_id in self._cancelled
            self._cancelled.discard(job_id)
        if cancelled:
            self.store.update(
                job_id, status="cancelled", finished_at=now_iso(), error="キャンセルされました"
            )
            return

        latest = self.store.get(job_id) or job
        self.store.update(
            job_id,
            status="succeeded" if ok else "failed",
            finished_at=now_iso(),
            error=None if ok else latest.get("error"),
        )

    def _run_episode(self, job: dict, log_path: Path) -> bool:
        s = self.settings
        cmd: list[str] = [str(s.python), "process_unified.py", job["spotify_url"]]
        if job.get("language"):
            cmd += ["--language", job["language"]]
        if job.get("llm_backend"):
            cmd += ["--llm-backend", job["llm_backend"]]
        if job.get("no_verify"):
            cmd.append("--no-verify")
        if job.get("no_notion"):
            cmd.append("--no-notion")

        ok = self._spawn(job["id"], cmd, log_path, s.episode_timeout, header="パイプライン実行")
        text = self._read_log(log_path)

        notion_url = self._extract_notion_url(text)
        if notion_url:
            self.store.update(job["id"], notion_url=notion_url)
        if not ok:
            self.store.update(job["id"], error=self._tail_error(text))
            return False

        # 追加指示があれば、生成されたページを対象に claude へ引き継ぐ
        prompt = (job.get("prompt") or "").strip()
        if prompt:
            follow_up = self._compose_followup_prompt(job, notion_url, prompt)
            ok = self._run_claude(job["id"], follow_up, log_path, header="追加指示を実行")
        return ok

    def _run_ask(self, job: dict, log_path: Path) -> bool:
        prompt = (job.get("prompt") or "").strip()
        if not prompt:
            self.store.update(job["id"], error="prompt が空です")
            return False
        if job.get("spotify_url"):
            prompt = f"対象エピソード: {job['spotify_url']}\n\n{prompt}"
        return self._run_claude(job["id"], prompt, log_path, header="依頼を実行")

    def _compose_followup_prompt(
        self, job: dict, notion_url: Optional[str], prompt: str
    ) -> str:
        target = notion_url or job.get("spotify_url") or ""
        return (
            "podcast-notes-automation で、たった今 1 エピソードのノートを生成しました。\n"
            f"Spotify URL: {job.get('spotify_url')}\n"
            f"生成された Notion ページ: {target or '(ログから特定してください)'}\n\n"
            "このページに対して、以下の追加依頼を実行してください。\n"
            "Notion への反映まで完了させ、最後に何をしたかを 3 行以内で報告してください。\n\n"
            f"--- 追加依頼 ---\n{prompt}\n"
        )

    def _run_claude(self, job_id: str, prompt: str, log_path: Path, header: str) -> bool:
        s = self.settings
        cmd = [s.claude_bin, "-p", prompt, "--permission-mode", s.claude_permission_mode]
        ok = self._spawn(job_id, cmd, log_path, s.ask_timeout, header=header)
        text = self._read_log(log_path)
        fields: dict[str, Any] = {"result_text": self._tail(text, 4000)}
        notion_url = self._extract_notion_url(text)
        if notion_url:
            fields["notion_url"] = notion_url
        if not ok:
            fields["error"] = self._tail_error(text)
        self.store.update(job_id, **fields)
        return ok

    def _spawn(
        self, job_id: str, cmd: list[str], log_path: Path, timeout: int, header: str
    ) -> bool:
        s = self.settings
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n===== {header} ({now_iso()}) =====\n")
            log.write(f"$ {' '.join(shlex.quote(c) for c in cmd)}\n\n")
            log.flush()
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(s.project_dir),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # killpg でツリーごと止められるように
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
            except (FileNotFoundError, PermissionError) as exc:
                log.write(f"\n[起動失敗] {exc}\n")
                self.store.update(job_id, error=f"コマンドを起動できません: {exc}")
                return False

            with self._lock:
                self._current[job_id] = proc
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill_tree(proc, signal.SIGKILL)
                proc.wait()
                log.write(f"\n[タイムアウト] {timeout} 秒を超えたため停止しました\n")
                self.store.update(job_id, error=f"タイムアウト（{timeout}秒）")
                return False
            finally:
                with self._lock:
                    self._current.pop(job_id, None)
            log.write(f"\n[終了コード] {code}\n")
            return code == 0

    # -- ログ補助 ---------------------------------------------------------

    @staticmethod
    def _read_log(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _extract_notion_url(text: str) -> Optional[str]:
        matches = NOTION_URL_RE.findall(text)
        return matches[-1] if matches else None

    @staticmethod
    def _tail(text: str, limit: int) -> str:
        return text[-limit:] if len(text) > limit else text

    @staticmethod
    def _tail_error(text: str) -> str:
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        return "\n".join(lines[-12:]) or "不明なエラー"
