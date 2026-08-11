# ADR 0003：普通用户 Web UI（React + Tailwind）最小可行方案

- 状态：Proposed
- 日期：2026-08-11
- 作用域：本地 Recruiter Web 工作台的下一代前端；不改变平台访问、认证或合规策略

## 背景

`boss-agent-cli` 的主要接口仍面向 CLI / MCP / AI Agent。仓库已经有本地 Recruiter Web 工作台，但当前 UI 更适合作为工程控制台；普通招聘用户需要更清晰的任务状态、候选人筛选结果、人工复核和配置入口。

本 ADR 只讨论前端体验层。平台请求、浏览器/CDP、AI 调用、持久化和 assisted/research 模式判断继续由 Python 后端负责。前端不得复制这些策略，也不得出现能够绕过后端合规门控的“隐藏开关”。

## 决策

采用 **React + TypeScript + Tailwind CSS + Vite** 构建独立前端源码，并在发布时产出纯静态资源，由现有 Python Recruiter Web server 提供。生产运行不要求 Node.js 常驻进程。

第一阶段只消费现有本地 `/api/*` 能力；若接口缺少 UI 所需字段，优先扩展明确的本地 DTO，而不是让浏览器直接访问招聘平台。

### 1. 部署边界

```text
Browser (localhost)
  |
  | same-origin JSON
  v
Recruiter Web server (Python, loopback + local token + Host/Origin guard)
  |
  +-- local stores / task manager / AI service
  +-- compliance gate (assisted / research)
  +-- platform adapters / CDP (only when an existing backend capability permits it)
```

前端**不得**：

- 直接请求 BOSS、智联、51job 或其他招聘平台；
- 读取浏览器 cookie、token、stoken、security_id 等凭据并持久化；
- 在 URL、LocalStorage、日志、错误上报或导出文件中保存认证信息；
- 自行重试验证码、风控、限流或被后端阻断的动作；
- 把 research 模式包装成默认开启的产品能力。

### 2. MVP 页面

1. **概览**：本地任务状态、待复核数量、最近一次筛选时间、AI 配置健康状态；不展示凭据。
2. **职位**：查看本地职位 / JD、启用或停用筛选目标；远端同步必须显示其后端能力和当前 operating mode。
3. **候选人**：列表、详情、版本、评分解释、风险标记；默认只展示本地已获取数据。
4. **人工复核**：回复草稿、verification-required、automation review；所有真实发送/联系方式动作都明确标记“将在平台产生外部副作用”。
5. **任务**：运行中 / 已完成 / 失败任务、可恢复 checkpoint、错误信封和恢复建议。
6. **设置**：AI provider/model、本地模型、工作模式和安全限制；敏感值只允许重新输入，不提供“显示原值”。

不进入 MVP：自动投递、批量触达、验证码处理、平台风控绕过、招聘者侧候选人批量搜索、51job scraper。

### 3. 路由与状态

建议路由：

- `/`：Overview
- `/jobs`
- `/candidates`
- `/candidates/:candidateKey`
- `/reviews`
- `/tasks`
- `/settings`

服务端状态通过现有 API 获取；MVP 不引入全局 Redux。优先使用 React Query/TanStack Query 管理请求缓存和轮询，页面本地交互使用 React state。

任务轮询必须遵循现有 UI reliability 约束：瞬时失败可有限重试，连续失败进入明确终态，不允许无限静默轮询。

### 4. 组件边界

建议最小组件层：

- `AppShell`：导航、全局模式标识、连接状态；
- `CapabilityBadge`：available / blocked / requires-research / not-supported；
- `TaskStatus`：queued/running/completed/failed/verification-required；
- `CandidateScoreCard`：分数、证据、风险标记，不把 AI 分数伪装成录用结论；
- `ReviewActionPanel`：批准/拒绝/返回平台人工处理；
- `ErrorEnvelope`：结构化展示 code/message/recovery_action；
- `SensitiveInput`：API key 等仅写入，不回显持久化值。

### 5. 合规与安全

后端是唯一策略真源。UI 只根据后端返回值解释状态，不重新实现 `require_compliance_allowed`。

- assisted 模式：保持默认低风险；后端阻断的能力在 UI 中禁用并解释原因。
- research 模式：必须由用户显式配置；UI 显示醒目标识、预算、页数/请求上限和 kill switch。
- 风控/验证码：收到 `ACCOUNT_RISK`、`PLATFORM_VERIFICATION_REQUIRED`、`RATE_LIMITED` 等状态立即停止自动轮询或动作重试，并给出人工处理入口。
- 外部副作用：发送消息、交换联系方式等必须复用后端 review/pending/checkpoint 机制，不允许前端“直接请求平台”。
- 招聘公平性：UI 展示 JD-specific 评分证据，但不得以年龄、性别、婚育、民族、健康等受保护属性提供筛选控件或排序维度。

### 6. API 适配原则

MVP 优先复用现有 API：bootstrap、auth status、AI config、jobs、candidates、tasks、review/draft 等。

新增 DTO 时遵循：

- 只返回页面实际需要的字段；
- 候选人标识使用后端已有的稳定本地 key，不把平台临时 token 作为前端主键；
- 错误继续使用统一 JSON envelope；
- 所有日期使用带时区 ISO 8601；
- 不新增浏览器到第三方平台的 CORS 权限。

### 7. 前端目录建议

```text
web-ui/
  package.json
  vite.config.ts
  src/
    app/
    api/
    components/
    features/
      jobs/
      candidates/
      reviews/
      tasks/
      settings/
    routes/
  tests/
```

构建产物复制到 Python package 的静态资源目录；源码和构建产物的更新方式应在后续实现 PR 中固定，避免提交不可追踪的手工 bundle。

### 8. 测试策略

- 组件单测：Vitest + Testing Library；
- API contract：用脱敏 fixture 覆盖正常、空状态、401/403、风控、任务失败和字段缺失；
- 浏览器 smoke：Playwright 仅访问 loopback 测试 server，不访问真实招聘平台；
- Python 侧继续保留现有 Web API 和安全边界测试；
- 测试 fixture 禁止真实 cookie/token/security_id/简历/聊天内容。

### 9. 交付阶段

**Phase A — 静态 shell**：Vite/Tailwind、AppShell、Overview、API client、现有 bootstrap 接入。

**Phase B — 只读工作流**：Jobs、Candidates、Tasks、结构化错误和模式提示。

**Phase C — 人工复核**：Review queue、草稿、verification-required；真实副作用继续由后端 checkpoint 执行。

**Phase D — 替换旧页面**：功能对齐和可访问性验证后，再决定是否移除当前 vanilla JS 页面；迁移期间两套 UI 不共享未审计的客户端持久状态。

## 备选方案

### 继续扩展当前 vanilla JS

优点是依赖少；缺点是候选人、任务、人工复核、设置继续增长后，状态管理和组件复用成本上升。适合作为维护模式，不建议作为下一代普通用户 UI 的主路线。

### Next.js / SSR

本项目是本地优先工具，不需要 SEO 或服务端 React 渲染；引入常驻 Node server 会扩大安装面和安全边界，因此不采用。

### Electron/Tauri

可提供桌面封装，但会把“本地 Web UI”升级为发行/签名/自动更新问题。MVP 先验证浏览器 UI，不在本 ADR 引入桌面运行时。

## 后果

正向影响：普通用户入口与 Agent/CLI 解耦；React 组件适合逐步增加工作流；生产仍保持单个 Python 服务；合规逻辑继续集中在后端。

成本：新增 Node 前端开发依赖、构建步骤和 JS 测试矩阵；需要明确静态产物更新策略；现有 Web UI 在迁移期仍需维护。

## 验收条件

后续实现 PR 至少满足：

- 默认 assisted 模式不因新 UI 获得额外平台权限；
- 浏览器 Network 面板中不存在直接第三方招聘平台请求；
- LocalStorage/SessionStorage/URL 中不存在 cookie/token/security_id；
- 风控和 verification-required 不自动重试；
- 全部测试使用脱敏 fixture；
- `uv run pytest tests/ -q`、`uv run ruff check src/ tests/ mcp-server/`、`uv run mypy src/boss_agent_cli` 保持通过；
- 前端 lint/typecheck/test/build 在独立 CI job 中通过。

## 与 51job Roadmap 的关系

本 ADR 不改变 51job 的准入结论。`docs/research/platforms/51job.md` 仍是 source of truth：在稳定只读入口和脱敏响应证据不足时，51job 保持 `NOT_SUPPORTED`，Web UI 也不得通过 DOM 抓取或 RPA 绕过该门槛。
