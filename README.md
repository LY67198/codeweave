# CodeWeave

> 受 Claude Code 启发的多 Agent 编码助手,基于 LangGraph 构建。
> 多个 Agent 像织机上的线一样协作,把代码编织出来。

[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.8-blue)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1.3.11-green)](https://github.com/langchain-ai/langchain)
[![Python](https://img.shields.io/badge/Python-3.12+-yellow)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

## ✨ 功能特性

### ✅ 已完成(Phase 1 + 2 + 3 + 4)

- **多 Agent 架构** — Supervisor 调度 Explorer / Coder / Reviewer / Executor / Compact(Coder / Reviewer 仍占位,Phase 4+ LLM 接入)
- **Tool System** — `ToolRegistry` + 6 个工具:`read_file` / `write_file` / `edit_file` / `grep_files` / `run_bash` / `todo_write`
- **WORK_DIR 沙箱** — 所有文件工具强制工作目录边界
- **HITL 权限审批** — 危险 bash 命令通过 `langgraph.types.interrupt` 暂停 graph 等用户批准
- **标准 ReAct** — Executor ⇄ Tools 双节点循环,`Command.goto` 路由
- **Plan Mode** — 通过 `plan_mode_safe` 标志过滤只读工具
- **Checkpoint & Resume** — PostgreSQL `PostgresSaver` 持久化对话
- **Audit Log** — 工具调用 / 节点流转 / compact 事件写到 `audit_events` 表,可重放可调优
- **Token Usage 记账** — 每 LLM 调用写一行 `token_usage`,按模型聚合
- **Auto-Compaction(LLM 摘要)** — `compact_check` graph 入口 + Celery 后台异步摘要;超出阈值自动 dispatch,下回合生效;支持无 reduction 检测
- **Long-term Store** — `InMemoryStoreShim` 线程安全,namespace 隔离(`codeweave:global` / `codeweave:project`);Phase 4 换 PostgresStore
- **Celery 异步** — `compact_thread` 任务(retry x3 + acks_late + 5min hard kill),60s token 聚合 + 7d compact_results 清理
- **Alembic 迁移** — 首版 migration `0001_init_audit_compact_token` 建 3 张表 + 索引
- **真实 LLM 验证** — DeepSeek v4-flash / v4-pro 端到端跑通(compact 摘要真调用 LLM 回写,116 单测 + 6 集成测)

### ✅ Phase 4 已完成(FastAPI + SSE)

- **REST API + SSE 流** — `/api/v1/threads/{id}/messages`(SSE)/ `resume`(HITL)/ `state` / `timeline` / `cost`
- **工程化 lifespan** — PostgresSaver + Redis + Audit + Store + graph LRU 缓存
- **OpenAPI 3.1** — `/docs` Swagger UI + `/openapi.json`
- **`/readyz` k8s probe** — DB + Redis 健康检查
- **Trace ID** — `X-Request-ID` header 自动注入 + 流到 audit_events

### 🔜 计划中(Phase 5–7)

- **Vue 3 Web SPA** — 主客户端(Phase 5,会接 Phase 4 的 FastAPI + SSE)
- **`cw` CLI** — 终端客户端(Phase 6,同上)
- **Skills & MCP** — Markdown skills + Model Context Protocol(Phase 7)
- **Nginx + Docker Demo** — 一条命令启动生产环境(Phase 7)
- **Coder / Reviewer LLM 实装** — 用工具调用写代码 + 跑 build/test 反馈(Phase 7 视需要而定)

## 🏗️ 架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Vue 3 SPA   │     │  CLI (cw)    │     │  FastAPI     │
│  (Web UI)    │     │  (Terminal)  │     │  Backend     │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┴────────────────────┘
                            │ REST + SSE
                            ▼
              ┌──────────────────────────┐
              │   LangGraph Agent        │
              │   ┌──────────────────┐  │
              │   │  Plan Subgraph   │  │
              │   │  (read-only)     │  │
              │   └────────┬─────────┘  │
              │            ▼             │
              │   ┌──────────────────┐  │
              │   │ Execute Subgraph │  │
              │   │ (read+write)     │  │
              │   └──────────────────┘  │
              └──────────┬───────────────┘
                         │
              ┌──────────┴───────────┐
              ▼                      ▼
        ┌──────────┐          ┌──────────┐
        │PostgreSQL│          │  Redis   │
        │PostgresSaver         │Celery+Cache
        └──────────┘          └──────────┘
```

## 📚 文档

- **[设计文档](docs/superpowers/specs/2026-07-08-codeweave-design.md)** — 完整架构 spec
- **[Phase 2 Tool System 设计](docs/superpowers/specs/2026-07-08-phase2-tool-system-design.md)** — Tool System 设计 spec
- **[Phase 3 Persistence + Celery 设计](docs/superpowers/specs/2026-07-08-phase3-persistence-celery-design.md)** — audit / store / compact 设计 spec
- **Demo 脚本**(即将推出)
- **[API 路由速查](backend/src/codeweave/api/README.md)** — FastAPI 全部 9 个端点 + curl 4 场景(HITL / SSE / 重连)
- **OpenAPI 3.1 schema** — 启动后访问 `http://localhost:8000/docs` 看 Swagger UI

## 🚀 快速开始

```bash
# 1. 启动基础设施(PostgreSQL + Redis)
docker compose up -d

# 2. 安装 backend 依赖
uv sync --all-packages

# 3. 配置环境变量(填入真实 API key)
cp .env.example .env
# 编辑 .env:设置 OPENAI_API_KEY=sk-... 和 MODEL_NAME=deepseek-v4-flash

# 4. 跑 Alembic 迁移(建 3 张表:audit_events / compact_results / token_usage)
uv run --project backend alembic upgrade head

# 5. 跑测试(116 unit + 6 integration,约 5 秒)
DATABASE_URL=postgresql+psycopg://codeweave:codeweave_dev@localhost:5432/codeweave_test \
  uv run --project backend python -m pytest backend/tests/

# 6. 真实 LLM 验证:端到端 compact(需要 Postgres + Redis + 真 API key)
DATABASE_URL=... \
  uv run --project backend --env-file .env \
    python -m pytest backend/tests/integration/test_compact_real_llm.py -v -m llm

# 7. 起 Celery worker(独立终端)
uv run --project backend celery -A codeweave.tasks worker -Q codeweave -l info

# 8. 起 Celery beat(独立终端,跑 60s token 聚合 + 7d cleanup)
uv run --project backend celery -A codeweave.tasks beat -l info

# 9. 用 ReAct tool 跑一遍读文件(无需 LLM,纯工具演示)
cd D:/Mini_Code && uv run --project backend python -c "
from codeweave.graphs.execute_graph import build_execute_graph
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage
app = build_execute_graph().compile(checkpointer=InMemorySaver())
r = app.invoke(
    {'messages': [HumanMessage(content='用 read_file 读 backend/src/codeweave/tools/registry.py,简要回答。')],
     'todos': [], 'plan_mode': False, 'agent_history': []},
    config={'configurable': {'thread_id': 'demo'}, 'recursion_limit': 15},
)
print('final answer:', r['messages'][-1].content[:200])
"

# 10. 启 FastAPI 服务器(Phase 4)
make serve
# 浏览 http://localhost:8000/docs 看交互式 API

# 11. 端到端 curl(普通对话流)
curl -N -X POST http://localhost:8000/api/v1/threads/demo/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "读 backend/src/codeweave/api/main.py,简要回答。"}'

# 12. 前端(Phase 5)/ CLI(Phase 6)— 即将推出
```

**注意:** 所有 `uv run` 命令必须从**项目根目录** `D:/Mini_Code/` 运行(不能从 `backend/`),因为 `pydantic-settings` 按 CWD 解析 `.env`。

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| Agent 框架 | LangGraph 1.2.8 + LangChain 1.3.11 |
| Backend | FastAPI + sse-starlette |
| Frontend | Vue 3 + Vite + Pinia + Element Plus |
| CLI | Python + Rich + httpx |
| LLM | OpenAI 兼容(DeepSeek / Qwen / GLM / ...) |
| Checkpoint | PostgreSQL(LangGraph PostgresSaver) |
| 异步任务 | Celery + Redis |
| 反向代理 | Nginx |

## 🎯 设计哲学:Harness Engineering

`Agent = Model + Harness`

"Harness" 是模型周围的一切:工具、上下文、约束、循环、记忆、权限。CodeWeave 显式实现了 6 个要素:

1. **Context Architecture** — RootState + Reducer + Memory Store
2. **Architecture Constraints** — Plan Mode 只读过滤 + Permission 白名单
3. **Self-Validation Loop** — Reviewer + Executor 反馈循环
4. **Context Isolation** — Plan Subgraph(只读)vs Execute Subgraph(读写)
5. **Entropy Governance** — Token 计数 + Auto-compaction + Recursion limit
6. **Replaceability** — LLM Provider 抽象 + 可插拔存储

## 📦 项目结构

```
codeweave/
├── backend/
│   ├── src/codeweave/
│   │   ├── agents/     # supervisor / explorer / coder / reviewer / executor / compact
│   │   │               # compact_check_node(Phase 3 接 execute_graph 入口)
│   │   │               # coder / reviewer 仍占位,Phase 4+ LLM 接入
│   │   ├── graphs/     # root / plan_graph / execute_graph
│   │   │               # execute_graph START → compact_check ⇢ executor ⇄ tools
│   │   ├── state/      # RootState / PlanState / ExecuteState + reducers
│   │   ├── tools/      # ✅ registry + file_tools + bash_tools + todo_tools
│   │   │               # 每个 tool 加 audit 装饰 emit tool_call 事件
│   │   ├── persistence/  # PostgresSaver + audit.py(AuditLogger) + store.py(InMemoryStoreShim)
│   │   ├── db/         # ✅ SQLAlchemy 2.x base + ORM + Alembic(3 张表 + partial unique)
│   │   ├── config/     # Settings + model provider
│   │   ├── services/   # ✅ token_tracker + compact_logic 纯函数
│   │   ├── tasks/      # ✅ Celery + compact_thread + token_aggregate + cleanup
│   │   ├── prompts/    # ✅ compact.jinja 中文摘要模板
│   │   └── api/        # ✅ Phase 4 FastAPI routes + routers/ + sse.py + README
│   └── tests/          # 116 unit + 6 integration
├── frontend/          # (Phase 5) Vue 3 SPA
├── cli/               # (Phase 6) cw terminal client
├── skills/            # (Phase 7) Built-in Skills
├── deploy/            # (Phase 7) Nginx + Docker config
├── docs/superpowers/  # Specs & plans(本地,gitignore)
└── docker-compose.yml
```

## 🤝 灵感来源

CodeWeave 灵感来自 [Claude Code](https://docs.claude.com/en/docs/claude-code),但构建在不同的技术栈上(LangGraph + Vue 3 + FastAPI),采用多客户端架构。我们保留 Claude Code 的 UX(Plan Mode / Sub-agents / Skills / MCP),同时基于 LangGraph 的声明式 StateGraph 模型实现。

## 🪟 Windows (PowerShell) 等价命令

`make` 在 Windows 上不一定可用,可直接用 `uv` 等价命令(从项目根 `D:\Mini_Code\` 运行):

```powershell
# Celery worker
uv run --project backend celery -A codeweave.tasks worker -Q codeweave -l info

# Celery beat(定时任务调度)
uv run --project backend celery -A codeweave.tasks beat -l info

# Alembic 数据库迁移
uv run --project backend alembic upgrade head
uv run --project backend alembic revision --autogenerate -m "your message"
uv run --project backend alembic downgrade -1
```

## 📄 许可证

[MIT](LICENSE)
