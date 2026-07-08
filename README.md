# CodeWeave

> A multi-agent coding assistant inspired by Claude Code, built on LangGraph.
> Multiple agents collaborate like threads on a loom to weave code together.

[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.8-blue)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1.3.11-green)](https://github.com/langchain-ai/langchain)
[![Python](https://img.shields.io/badge/Python-3.12+-yellow)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

## ✨ Features

### ✅ Done (Phase 1 + Phase 2)

- **Multi-Agent Architecture** — Supervisor orchestrates Explorer / Coder / Reviewer / Executor / Compact
- **Tool System** — `ToolRegistry` + 6 tools: `read_file` / `write_file` / `edit_file` / `grep_files` / `run_bash` / `todo_write`
- **WORK_DIR Sandbox** — All file tools enforce work-directory boundary
- **HITL Permission** — Dangerous bash commands pause graph for human approval via `langgraph.types.interrupt`
- **Standard ReAct** — Executor ⇄ Tools dual-node loop with `Command.goto` routing
- **Plan Mode** — Read-only tool filtering via `plan_mode_safe` flag
- **Checkpoint & Resume** — PostgreSQL `PostgresSaver` for conversation persistence
- **Real LLM Verified** — End-to-end runs with DeepSeek v4-flash / v4-pro

### 🔜 Planned (Phase 3–7)

- **Auto-Compaction** — Context window management with intelligent summarization (Phase 3)
- **Sub-agents** — Parallel task dispatch via LangGraph `Send` primitive (Phase 3)
- **SSE Streaming** — Token-by-token output via FastAPI (Phase 4)
- **Vue 3 Web SPA** — Primary client (Phase 5)
- **`cw` CLI** — Terminal client (Phase 6)
- **Skills & MCP** — Markdown skills + Model Context Protocol (Phase 7)
- **Nginx + Docker Demo** — One-command production setup (Phase 7)

## 🏗️ Architecture

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

## 📚 Documentation

- **[Design Document](docs/superpowers/specs/2026-07-08-codeweave-design.md)** — Complete architecture spec
- **Demo Script** (coming soon)
- **API Reference** (auto-generated from FastAPI)

## 🚀 Quick Start

```bash
# 1. Start infrastructure (PostgreSQL + Redis)
docker compose up -d

# 2. Install backend dependencies
uv sync --all-packages

# 3. Configure env (set real API key)
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-... and MODEL_NAME=deepseek-v4-flash

# 4. Run tests (73 unit + 5 integration, ~1.5s)
uv run --project backend python -m pytest backend/tests/

# 5. Verify end-to-end with real LLM
#    Expected output: HumanMessage → AIMessage(tool_call) → ToolMessage → AIMessage(final answer)
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

# 6. Frontend (Phase 5) / CLI (Phase 6) — coming soon
# cd ../frontend && pnpm install && pnpm dev
# cd ../cli && uv sync && cw
```

**Note:** All `uv run` commands must be run from the project root `D:/Mini_Code/` (not from `backend/`) — `pydantic-settings` resolves `.env` relative to CWD.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | LangGraph 1.2.8 + LangChain 1.3.11 |
| Backend | FastAPI + sse-starlette |
| Frontend | Vue 3 + Vite + Pinia + Element Plus |
| CLI | Python + Rich + httpx |
| LLM | OpenAI-compatible (DeepSeek/Qwen/GLM/...) |
| Checkpoint | PostgreSQL (LangGraph PostgresSaver) |
| Async Tasks | Celery + Redis |
| Reverse Proxy | Nginx |

## 🎯 Design Philosophy: Harness Engineering

`Agent = Model + Harness`

The "harness" is everything around the model: tools, context, constraints, loops, memory, permissions. CodeWeave explicitly implements 6 elements:

1. **Context Architecture** — RootState + Reducer + Memory Store
2. **Architecture Constraints** — Plan Mode read-only filtering, Permission whitelist
3. **Self-Validation Loop** — Reviewer + Executor feedback loops
4. **Context Isolation** — Plan Subgraph (read) vs Execute Subgraph (write)
5. **Entropy Governance** — Token counting + Auto-compaction + Recursion limit
6. **Replaceability** — LLM Provider abstraction, Pluggable storage

## 📦 Project Structure

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
├── docs/superpowers/  # Specs & plans (local only, gitignored)
└── docker-compose.yml
```

## 🤝 Inspiration

CodeWeave is inspired by [Claude Code](https://docs.claude.com/en/docs/claude-code) but built on a different stack (LangGraph + Vue 3 + FastAPI) with a multi-client architecture. We preserve Claude Code's UX (Plan Mode / Sub-agents / Skills / MCP) while implementing on LangGraph's declarative StateGraph model.

## 📄 License

[MIT](LICENSE)