# CodeWeave

> 受 Claude Code 启发的多 Agent 编码助手,基于 LangGraph 构建。
> 多个 Agent 像织机上的线一样协作,把代码编织出来。

[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.8-blue)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1.3.11-green)](https://github.com/langchain-ai/langchain)
[![Python](https://img.shields.io/badge/Python-3.12+-yellow)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

## ✨ 功能特性

### ✅ 已完成(Phase 1 + Phase 2)

- **多 Agent 架构** — Supervisor 调度 Explorer / Coder / Reviewer / Executor / Compact
- **Tool System** — `ToolRegistry` + 6 个工具:`read_file` / `write_file` / `edit_file` / `grep_files` / `run_bash` / `todo_write`
- **WORK_DIR 沙箱** — 所有文件工具强制工作目录边界
- **HITL 权限审批** — 危险 bash 命令通过 `langgraph.types.interrupt` 暂停 graph 等用户批准
- **标准 ReAct** — Executor ⇄ Tools 双节点循环,`Command.goto` 路由
- **Plan Mode** — 通过 `plan_mode_safe` 标志过滤只读工具
- **Checkpoint & Resume** — PostgreSQL `PostgresSaver` 持久化对话
- **真实 LLM 验证** — DeepSeek v4-flash / v4-pro 端到端跑通

### 🔜 计划中(Phase 3–7)

- **Auto-Compaction** — 上下文窗口管理 + 智能摘要(Phase 3)
- **Sub-agents** — 通过 LangGraph `Send` 原语并行派发任务(Phase 3)
- **SSE 流式输出** — FastAPI 逐 token 输出(Phase 4)
- **Vue 3 Web SPA** — 主客户端(Phase 5)
- **`cw` CLI** — 终端客户端(Phase 6)
- **Skills & MCP** — Markdown skills + Model Context Protocol(Phase 7)
- **Nginx + Docker Demo** — 一条命令启动生产环境(Phase 7)

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
- **Demo 脚本**(即将推出)
- **API 参考**(Phase 4 FastAPI 自动生成)

## 🚀 快速开始

```bash
# 1. 启动基础设施(PostgreSQL + Redis)
docker compose up -d

# 2. 安装 backend 依赖
uv sync --all-packages

# 3. 配置环境变量(填入真实 API key)
cp .env.example .env
# 编辑 .env:设置 OPENAI_API_KEY=sk-... 和 MODEL_NAME=deepseek-v4-flash

# 4. 跑测试(73 unit + 5 integration,约 1.5 秒)
uv run --project backend python -m pytest backend/tests/

# 5. 用真实 LLM 验证端到端
#    预期输出:HumanMessage → AIMessage(tool_call) → ToolMessage → AIMessage(最终回答)
cd D:/Mini_Code && PATH="$HOME/.cache/mimocode/bin:$PATH" uv run --project backend python -c "
from codeweave.graphs.execute_graph import build_execute_graph
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage
app = build_execute_graph().compile(checkpointer=InMemorySaver())
r = app.invoke(
    {'messages': [HumanMessage(content='用 read_file 读 backend/src/codeweave/tools/registry.py,简要回答。')],
     'todos': [], 'plan_mode': False, 'agent_history': []},
    config={'configurable': {'thread_id': 'demo'}, 'recursion_limit': 15},
)
print('agent_history:', [h['decision'] for h in r['agent_history']])
print('final answer:', r['messages'][-1].content[:200])
"

# 6. 前端(Phase 5)/ CLI(Phase 6)— 即将推出
# cd ../frontend && pnpm install && pnpm dev
# cd ../cli && uv sync && cw
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
│   │   ├── graphs/     # root / plan_graph / execute_graph
│   │   ├── state/      # RootState / PlanState / ExecuteState + reducers
│   │   ├── tools/      # ✅ registry + file_tools + bash_tools + todo_tools
│   │   ├── persistence/  # PostgresSaver
│   │   ├── config/     # Settings + model provider
│   │   ├── api/        # (Phase 4) FastAPI routes
│   │   ├── services/   # (Phase 4) Celery + token tracker
│   │   └── prompts/    # (Phase 4) Jinja2 templates
│   └── tests/          # 73 unit + 5 integration
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
