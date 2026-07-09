---
name: codeweave-coder
description: codeweave Coder — 修改源文件,产出 unified diff
when_to_use: |
  当用户要求改文件、改函数、加 feature、refactor 时调用这个 skill。
  不要用来回答问题或跑只读查询 — 那些用 ReAct executor 路径。
priority: 50
---

## Workflow
1. 读目标区域现有代码(用 read_file),理解上下文
2. 用 file_write / file_edit 工具改文件(禁止触摸敏感路径)
3. 写最少必要的代码改动(YAGNI)

## Examples
(用户在 Phase 5 实现后积累,Phase 5 demo 留空)

## Pitfalls
- 不要触碰敏感路径(.ssh / .env / /etc 等) — 工具入口会拒
- 不要破坏现有 import 顺序或类型注解
- 不要为暂时用不到的边界 case 加防御代码
