# CodeWeave API — 路由速查表

启动:`make serve` 或 `cd backend && uv run uvicorn codeweave.api.main:app --reload`

## 端点(共 9)

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/v1/threads/{thread_id}/messages` | 推 user 输入,流 SSE |
| POST | `/api/v1/threads/{thread_id}/resume` | HITL 决策 |
| GET | `/api/v1/threads/{thread_id}/state` | 当前 checkpoint |
| GET | `/api/v1/threads/{thread_id}/timeline` | audit_events 时间线 |
| GET | `/api/v1/cost` | token 用量按模型聚合 |
| GET | `/healthz` | liveness |
| GET | `/readyz` | readiness(DB + Redis) |
| GET | `/docs` | Swagger UI |
| GET | `/openapi.json` | OpenAPI 3.1 schema |

## curl 4 场景

### 1. 普通对话
```bash
curl -N -H "Content-Type: application/json" -X POST \
  http://localhost:8000/api/v1/threads/demo-1/messages \
  -d '{"content": "读 backend/src/codeweave/api/main.py 头两行"}'
```
流输出 node_end / messages_update / done 事件。

### 2. HITL 触发(rm -rf 危险命令)
```bash
curl -N -X POST http://localhost:8000/api/v1/threads/demo-hitl/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "执行 rm -rf /tmp/test"}'
```
收到 `hitl_requested` event 后:
```bash
curl -N -X POST http://localhost:8000/api/v1/threads/demo-hitl/resume \
  -H "Content-Type: application/json" \
  -d '{"interrupt_id": "<from-hitl_event>", "decision": {"approve": true}}'
```

### 3. HITL 拒绝
同上,把 `{"approve": false}` 传入。

### 4. 断线重连
```bash
# 第一条流跑完后:
curl http://localhost:8000/api/v1/threads/demo-1/state
```
看到 messages / todos / compact_pending 的完整状态。

## Trace ID

每个请求接受 `X-Request-ID` header(自动生成若缺):
```bash
curl -H "X-Request-ID: my-trace-123" http://localhost:8000/api/v1/threads/x/state
```
回响应头会回同样 id。

## 错误响应

所有 4xx / 5xx 走 `ErrorBody`:
```json
{
  "code": "thread_not_found",
  "message": "thread x 在 PostgresSaver 里无任何 checkpoint",
  "trace_id": "trace-...",
  "details": null
}
```

## Phase 4 不覆盖(out of scope,Phase 7 polish)

- 鉴权 / multi-tenancy(暂无)
- WebSocket(SSE 够)
- Prometheus metrics
- nginx 上行