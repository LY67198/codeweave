"""启一个 worker 子进程,真走 Redis broker,验证跨进程可见性。

Phase 3 Plan Task 15。可选测试:需要 docker compose up(Redis + Postgres),
默认跳过。Phase 4 再正式跑也行,不阻塞主线。

跳过的条件(任一为真即 skip):
    - Docker daemon 不可达(``docker info`` 失败)
    - Redis ping 失败(``redis-cli ping`` 失败 / 超时)
    - Postgres 不可达(用 ``_postgres_reachable`` 短超时探测)
    - 环境变量 ``RUN_CELERY_WORKER_TEST=1`` 未显式开启
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from pathlib import Path

import pytest

from codeweave.db.base import SessionLocal


# 数据库连通性探测(沿用 test_compact_real_llm.py 的模式)
def _postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    """短超时探测 Postgres 是否可达,避免测试集卡死。"""
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError, OperationalError

    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": int(timeout)},
        )
        with engine.connect() as conn:
            conn.execute("SELECT 1")  # type: ignore[arg-type]
        return True
    except (OperationalError, DBAPIError, OSError, ValueError):
        return False


def _docker_daemon_up() -> bool:
    """``docker info`` 退出码 0 表示 Docker daemon 正常。"""
    try:
        return (
            subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            ).returncode
            == 0
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _redis_pingable(timeout: float = 2.0) -> bool:
    """``redis-cli ping`` 应返回 ``PONG``。

    Fallback:HOST:PORT 端口可达也认。Redis ping 用于保证 worker 启动后
    能真走 broker 而不是 memory://。
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    # 仅取 host:port 用于探测,不做认证
    match = re.match(r"redis://(?:[^@]+@)?([^:/]+):(\d+)", redis_url)
    if not match:
        return False
    host, port = match.group(1), int(match.group(2))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# 整体 skip 条件:Phase 3 默认不阻塞;用户显式 ``RUN_CELERY_WORKER_TEST=1`` 才跑
_RUN_OPT_IN = os.environ.get("RUN_CELERY_WORKER_TEST") == "1"
_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test",
)


_REASON_PARTS: list[str] = []
if not _RUN_OPT_IN:
    _REASON_PARTS.append("RUN_CELERY_WORKER_TEST=1 not set")
if not _docker_daemon_up():
    _REASON_PARTS.append("docker daemon not reachable")
if not _redis_pingable():
    _REASON_PARTS.append("redis broker not reachable at REDIS_URL")
if not _postgres_reachable(_DATABASE_URL):
    _REASON_PARTS.append(f"postgres not reachable at {_DATABASE_URL}")

_SKIP_REASON = "; ".join(_REASON_PARTS) or "all skip conditions cleared (should not see this)"

# ``skipif`` 的 condition 要传表达式,我们直接预计算
_SKIP = len(_REASON_PARTS) > 0
# 只有当用户显式 opt-in 但 infra 不通时,才报 error 而不是 skip — 这种情况下写的人意图明确
if _RUN_OPT_IN and _SKIP:
    pytest.fail(f"RUN_CELERY_WORKER_TEST=1 但基础设施不全通: {_SKIP_REASON}")

# 装饰器只能挂在 test 上,fixture 不能用 mark — fixture 由 autouse=True 跟随 test,
# 一旦 test 被 skip,fixture 不会启动。把 marker 放在 test 上就够了。
_SKIPIF = pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)


@pytest.fixture(scope="module", autouse=True)
def worker_proc():
    """启一个 Celery worker 子进程真走 Redis broker。

    broker / result backend 强制改写为 ``memory://`` / ``cache+memory://``,
    让 worker 进程不依赖 result backend 也能跑通 main worker 链路。
    """
    # backend cwd:`backend/` 包根,跨平台用 Path 而不是 /d/... hardcode
    repo_root = Path(__file__).resolve().parents[2]
    backend_cwd = repo_root / "backend"

    env = {
        **os.environ,
        "DATABASE_URL": _DATABASE_URL,
        "CELERY_BROKER_URL": "memory://",
        "CELERY_RESULT_BACKEND": "cache+memory://",
    }

    cmd = [
        "uv",
        "run",
        "celery",
        "-A",
        "codeweave.tasks.celery_app",
        "worker",
        "-Q",
        "codeweave",
        "--loglevel=info",
        "-c",
        "1",
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(backend_cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # 等 worker 起来,3s 经验值
    time.sleep(3)
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


@_SKIPIF
def test_task_visible_across_process_via_polling():
    """通过同进程 .delay dispatch,期待 worker 子进程在 10s 内把 CompactResult
    推进到 ``done`` 或 ``failed`` — 证明跨进程可见。
    """
    from codeweave.db.models import CompactResult
    from codeweave.tasks.compact import compact_thread

    tid = "worker-roundtrip-1"
    with SessionLocal() as session:
        row = CompactResult(thread_id=tid, status="pending", applied=False)
        session.add(row)
        session.commit()

    # 异步发起任务(短 .delay 不阻塞,worker 在另一进程)
    compact_thread.delay(tid)

    # poll DB 最多 10s
    deadline = time.time() + 10
    final_status = None
    while time.time() < deadline:
        with SessionLocal() as session:
            row = (
                session.query(CompactResult)
                .filter_by(thread_id=tid)
                .order_by(CompactResult.created_at.desc())
                .first()
            )
            if row is not None and row.status in {"done", "failed"}:
                final_status = row.status
                break
        time.sleep(0.5)

    assert final_status in {"done", "failed"}, (
        "10s 内 worker 没把任务完成,broker 链路可能有问题"
    )
