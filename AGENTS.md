<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **intelligent-eval-platform** (3226 symbols, 6987 relationships, 282 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/intelligent-eval-platform/context` | Codebase overview, check index freshness |
| `gitnexus://repo/intelligent-eval-platform/clusters` | All functional areas |
| `gitnexus://repo/intelligent-eval-platform/processes` | All execution flows |
| `gitnexus://repo/intelligent-eval-platform/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

<!-- review:start -->
## 开发流程规范（收尾约束）

### 1. 每次修改后必须二次审查

任何代码 / 文档 / 配置改动在任务收尾前，必须执行一次完整自查（不得直接交付），至少覆盖：

- **静态校验**：后端 Python 改动运行语法 / 静态检查，前端 JS 改动运行 `node --check`（或其他项目可用的校验手段）；
- **逻辑复核**：对照需求与设计确认改动正确，重点检查边界条件、失败路径、并发与回滚是否遗漏；
- **回归检查**：确认改动未破坏既有功能（调用方、接口契约、文档一致性）；
- **安全复核**：密钥 / 敏感信息不入库、不入日志；路径与权限安全；异常响应不泄露内部细节；
- **文档同步**：受影响的 README / BRD / docs 是否同步更新；无残留调试输出、临时代码或死代码。

审查结论（通过，或发现并修复的问题清单）应在交付说明中简述。

### 2. 必须维护状态文档

- 维护 `docs/production-readiness-todo.md` 作为唯一的「已完成 / 待办」状态文档；
- 任务完成：将完成项写入「A. 已完成」并注明日期与内容，同时从待办区移除或标记；
- 新发现问题 / 新待办：按优先级（P0 / P1 / P2）写入「B. 生产化前待办」；
- 删除或归档条目必须注明去向，不允许无痕删除；
- 状态更新与代码改动一起提交，保持文档与实现同步。
<!-- review:end -->

<!-- frontend-design:start -->
## 前端体验与设计协作规范

- 前端需求说明的是业务目标与关键结构，不是页面设计的全部；实现前必须主动推演信息层级、状态、交互路径、异常/空数据反馈与可扩展性。
- 新页面或重构页面必须复用当前平台的视觉语言（导航、目录树、指标卡、表格、间距、颜色与反馈方式），不得以无层级的白色卡片堆叠替代已有设计体系。
- 涉及工作台、管理页或数据报告时，先按用户任务流组织页面：先呈现决策所需的摘要，再提供可定位、筛选、展开和追溯的明细。
- 在实施包含非显然设计判断的前端改动前，先向用户说明设计方案、关键取舍与待确认点；用户负责业务目标，助手负责补全展示逻辑、样式与交互细节。
- 详细规则维护于 `docs/frontend-design-guidelines.md`；新增或调整前端页面时必须遵循并在交付时说明设计复核结论。
<!-- frontend-design:end -->
