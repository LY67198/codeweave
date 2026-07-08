# CodeWeave

> A multi-agent coding assistant inspired by Claude Code, built on LangGraph.
> Multiple agents collaborate like threads on a loom to weave code together.

[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.8-blue)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1.3.11-green)](https://github.com/langchain-ai/langchain)
[![Python](https://img.shields.io/badge/Python-3.12+-yellow)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

## ✨ Features

- **5-Agent Architecture** — Supervisor orchestrates Explorer, Coder, Reviewer, and Executor
- **Plan Mode** — Read-only planning phase with explicit user approval (Claude Code style)
- **Sub-agents** — Parallel task dispatch via LangGraph's `Send` primitive
- **Multi-Client** — Vue 3 Web SPA + `cw` CLI + FastAPI backend
- **Streaming** — SSE-based token-by-token output
- **Checkpoint & Resume** — PostgreSQL-backed conversation persistence
- **Auto-Compaction** — Context window management with intelligent summarization
- **Skills & MCP** — Extensible via Markdown skills and Model Context Protocol
- **Harness Engineering** — Explicit 6-element design philosophy for reliable agents

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
# 1. Start infrastructure
docker compose up -d

# 2. Install backend
cd backend
uv sync
cp .env.example .env  # configure LLM API key

# 3. Install frontend
cd ../frontend
pnpm install
pnpm dev

# 4. Install CLI
cd ../cli
uv sync
cw  # start CLI client
```

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
├── backend/           # FastAPI + LangGraph Agent
├── frontend/          # Vue 3 SPA
├── cli/               # cw terminal client
├── skills/            # Built-in Skills
├── deploy/            # Nginx + Docker config
├── docs/              # Architecture & demo docs
└── docker-compose.yml
```

## 🤝 Inspiration

CodeWeave is inspired by [Claude Code](https://docs.claude.com/en/docs/claude-code) but built on a different stack (LangGraph + Vue 3 + FastAPI) with a multi-client architecture. We preserve Claude Code's UX (Plan Mode / Sub-agents / Skills / MCP) while implementing on LangGraph's declarative StateGraph model.

## 📄 License

[MIT](LICENSE)