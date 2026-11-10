#!/usr/bin/env python
"""本地 / 容器环境下的 worker 守护进程（systemd 之外的兜底方案）。

启动 3 个 ARQ worker（chat / rag / expense-review），任一进程退出后自动重启，
Ctrl+C 时统一优雅退出。

用法：
    uv run python scripts/run_workers.py                # 只起 worker
    uv run python scripts/run_workers.py --with-api     # 同时起 FastAPI（开发用）

生产环境优先使用 deploy/systemd/*.service，由 systemd 负责守护与开机自启。
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WORKERS = [
    ("chat-worker", "app.worker.chat_task.WorkerSettings"),
    ("rag-worker", "app.worker.rag_task.WorkerSettings"),
    # 没有它，所有新提交的报销单 AI 初审会一直卡在 pending
    ("review-worker", "app.worker.expense_review_task.WorkerSettings"),
]

RESTART_DELAY_SECONDS = 3


def _console_script(name: str) -> str:
    """定位当前虚拟环境里的可执行文件（Windows 为 .exe）。"""
    candidate = Path(sys.executable).parent / (
        f"{name}.exe" if os.name == "nt" else name
    )
    return str(candidate) if candidate.exists() else name


def _spawn(command: list[str]) -> subprocess.Popen:
    print(f"[supervisor] start: {' '.join(command)}", flush=True)
    return subprocess.Popen(command)


def main() -> int:
    parser = argparse.ArgumentParser(description="启动并守护 AgentFlow 的后台进程")
    parser.add_argument("--with-api", action="store_true", help="同时启动 FastAPI")
    args = parser.parse_args()

    arq = _console_script("arq")
    processes: dict[str, tuple[list[str], subprocess.Popen]] = {}

    def start_all() -> None:
        if args.with_api and "api" not in processes:
            port = os.getenv("APP_PORT", "18082")
            command = [
                _console_script("uvicorn"),
                "main:app",
                "--host",
                "0.0.0.0",
                "--port",
                port,
            ]
            processes["api"] = (command, _spawn(command))

        for name, target in WORKERS:
            if name in processes:
                continue
            command = [arq, target]
            processes[name] = (command, _spawn(command))

    stopping = False

    def handle_signal(signum, frame):  # noqa: ANN001, ARG001
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    start_all()
    print(
        "[supervisor] 已启动："
        + "、".join(processes.keys())
        + "；按 Ctrl+C 退出",
        flush=True,
    )

    try:
        while not stopping:
            time.sleep(1)
            for name, (command, process) in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                if stopping:
                    break
                print(
                    f"[supervisor] {name} 退出（code={code}），"
                    f"{RESTART_DELAY_SECONDS}s 后重启",
                    flush=True,
                )
                time.sleep(RESTART_DELAY_SECONDS)
                processes[name] = (command, _spawn(command))
    finally:
        for name, (_, process) in processes.items():
            if process.poll() is None:
                print(f"[supervisor] 停止 {name}", flush=True)
                process.terminate()
        for name, (_, process) in processes.items():
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print(f"[supervisor] 强制结束 {name}", flush=True)
                process.kill()

    return 0


if __name__ == "__main__":
    sys.exit(main())
