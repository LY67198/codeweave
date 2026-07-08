# 集成测试说明

本目录下是依赖真实外部服务的端到端测试,目前涵盖:

- `test_root_graph.py` — RootGraph + PostgresSaver 编译冒烟
- `test_executor_with_tools.py` — Executor 节点 + 真实工具注册中心
- `test_compact_graph_topology.py` — execute_graph 拓扑结构(spec §4.6)
- `test_compact_e2e.py` — Compact dispatch → apply 闭环(task_always_eager)
- `test_compact_race.py` — Compact 并发 dispatch 竞态(partial unique index)

## 前置条件

集成测试需要本地 **PostgreSQL 16**(`docker compose up postgres redis` 或
本地安装)。无 Postgres 时 `DATABASE_URL` 不会被识别,所有 e2e 用例会
`pytest.skip` 自动跳过。

```bash
# 1. 创建专用测试库(只一次)
createdb codeweave_test

# 2. 跑 alembic 迁移到 head
DATABASE_URL=postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test \
  uv run --project backend alembic upgrade head
```

## 跑测试

从仓库根目录 `D:/Mini_Code/` 执行(关键 — `Settings` 用相对 CWD 找 `.env`):

```bash
cd D:/Mini_Code
DATABASE_URL=postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test \
  uv run --project backend python -m pytest -v backend/tests/integration/
```

只跑 compact 端到端 + 竞态:

```bash
cd D:/Mini_Code
DATABASE_URL=postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test \
  uv run --project backend python -m pytest -v \
    backend/tests/integration/test_compact_e2e.py \
    backend/tests/integration/test_compact_race.py
```

## Celery 模式

`test_compact_e2e.py` 默认打开 `task_always_eager`,**不需要**真的启动
Celery worker/broker;`compact_thread.apply(...).get()` 在调用进程内同步
执行 task body 并返回 compact_results.id。

LLM 调用 `codeweave.tasks.compact.llm_summarize` 与
`_get_checkpointer` 都被 `unittest.mock.patch` 替换,无需真实 API key 或
PostgresSaver。

## 已知限制

- 本机若 Docker Desktop 未启动,Postgres 不可用,**所有集成测试会跳过**。
  这是预期行为,不是 bug。
- Compact e2e 用例不验证 `messages` 长度,只验证
  `new_messages` 中包含 SUMMARY 摘要内容(由 mock LLM 返回)。
- 并发测试依赖 partial unique index
  `uq_compact_pending_per_thread (thread_id) WHERE applied = false` —
  若迁移 `0001_phase3_persistence` 未生效,该测试会失败。
