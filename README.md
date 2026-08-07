<div align="center">

<img src="docs/assets/logo.svg" width="112" alt="boss-agent-cli logo">

# BOSS Recruit AI / boss-agent-cli

**本地招聘 AI 工作台：岗位画像 → 简历解析 → 证据化评分 → 候选人排序 → Kanban 流转 → 回复草稿 → 人工联系。**

同时保留原 `boss-agent-cli` 的 CLI、AI Agent、MCP 与求职者辅助能力。

[![CI](https://github.com/can4hou6joeng4/boss-agent-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/can4hou6joeng4/boss-agent-cli/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/can4hou6joeng4/boss-agent-cli/branch/master/graph/badge.svg)](https://codecov.io/gh/can4hou6joeng4/boss-agent-cli)
[![Python](https://img.shields.io/badge/Python-≥3.10-3776AB?logo=python&logoColor=white&style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/can4hou6joeng4/boss-agent-cli?style=flat-square)](https://github.com/can4hou6joeng4/boss-agent-cli/releases)
[![PyPI Downloads](https://img.shields.io/pypi/dm/boss-agent-cli?style=flat-square)](https://pypi.org/project/boss-agent-cli/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/can4hou6joeng4/boss-agent-cli/pulls)
[![MCP Toplist](https://mcptoplist.com/badge/glama%2Fcan4hou6joeng4%2Fboss-agent-cli.svg)](https://mcptoplist.com/server/glama%2Fcan4hou6joeng4%2Fboss-agent-cli)

[快速开始](docs/getting-started.md) · [Agent Quickstart](docs/agent-quickstart.md) · [Capability Matrix](docs/capability-matrix.md) · [平台风险](docs/platform-risk.md) · [排障](docs/troubleshooting.md) · [中文](README.md) | [English](README.en.md)

</div>

> [!NOTE]
> 本仓库基于 [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) 持续开发。原作者、MIT 许可证、CLI/MCP 架构与上游生态信息均保留；当前 fork 的招聘 AI Web 工作台、一键启动和招聘流程由 `zerlinpi/boss-agent-cli` 维护。当前 fork CI：<https://github.com/zerlinpi/boss-agent-cli/actions/workflows/ci.yml>。

> [!IMPORTANT]
> 项目定位是**招聘 Copilot / 本地招聘工作台**，不是无人值守招聘机器人。AI 只提供辅助评分、排序和回复草稿，不自动决定录用/淘汰，也不自动向候选人发送 BOSS 消息。默认遵循低风险、只读优先、用户主动触发的边界；被策略阻断的敏感命令返回 `COMPLIANCE_BLOCKED`，应回到平台官网或官方页面人工处理。

---

## 🚀 最快启动

### Windows 一键启动（推荐）

下载仓库 ZIP 或拉取 `master` 后，双击：

```text
start-recruiter-web.bat
```

首次启动会自动完成：

1. 检测 Python 3.10–3.14；
2. 无可用 Python 时尝试通过 `winget` 安装 Python 3.12；
3. 创建或修复项目独立 `.venv`；
4. 安装/更新项目依赖与 `pypdf`；
5. 检查 Patchright，并执行 `patchright install chromium`；
6. 启动本地 Web 服务；
7. 自动打开浏览器。

默认地址：

```text
http://127.0.0.1:8765/
```

关闭启动窗口即可停止服务。Chromium 下载失败不会阻止本地简历筛选，但 BOSS 浏览器登录可能需要重新安装 Chromium 或使用本机 Chrome。

### Docker 一键启动

Windows + Docker Desktop 双击：

```text
start-recruiter-docker.bat
```

停止：

```text
stop-recruiter-docker.bat
```

macOS / Linux：

```bash
docker compose -f docker-compose.recruiter.yml up -d --build
```

默认只发布到宿主机回环地址：

```text
127.0.0.1:8765
```

自定义端口：

```bash
BOSS_WEB_PORT=9000 docker compose -f docker-compose.recruiter.yml up -d --build
```

数据持久化在 Docker named volume：

```text
boss-recruiter-data
```

Docker 更适合本地文件筛选、候选人管理和 AI 工作流。BOSS 登录依赖真实浏览器环境，Windows 原生模式体验更完整；Docker 可通过 `BOSS_CDP_URL=http://host.docker.internal:9222` 连接用户主动开启的宿主机 Chrome 调试端口。

---

## 🎯 招聘工作流

```text
岗位 JD
  ↓
AI 岗位画像 / 可配置评分规则
  ↓
本地 PDF/DOCX/TXT/JSON 或授权范围内的 BOSS 候选人
  ↓
简历标准化 + 联系方式本地提取
  ↓
生成模型安全副本
  ↓
证据化维度评分 + 本地重算总分
  ↓
候选人排名 / 横向对比 / 风险与追问
  ↓
Kanban：新候选人 → 入围 → 面试 → 待定 → 录用/不合适
  ↓
AI 回复草稿 → 人工审核 → 人工联系
```

典型操作：

1. 在 **系统设置** 配置 AI；
2. 新建岗位并粘贴 JD；
3. 用 **AI 分析岗位** 生成评分维度和硬性要求；
4. 上传本地简历，或在明确授权的 Research Mode 下读取当前实现支持的招聘者数据；
5. 在 Dashboard 查看 Top 候选人和漏斗；
6. 在候选人工作台使用列表/Kanban、搜索、排序、批量流转和横向对比；
7. 打开候选人详情查看证据、风险、联系人和建议追问；
8. 生成回复草稿，人工审核后在官方渠道联系候选人。

---

## 🌟 主要能力

### 图形招聘控制台

| 能力 | 状态 |
| --- | --- |
| 本地 Web UI | ✅ |
| Windows 双击启动 | ✅ |
| Docker Compose 一键启动 | ✅ |
| Dashboard / 招聘漏斗 | ✅ |
| 多岗位配置 | ✅ |
| AI 分析 JD | ✅ |
| 自定义评分规则 | ✅ |
| 候选人列表 + Kanban | ✅ |
| 拖拽阶段流转 | ✅ |
| 搜索 / 过滤 / 排序 | ✅ |
| 批量状态更新 | ✅ |
| CSV 导出 | ✅ |
| 2–4 人横向比较 | ✅ |
| 任务历史 / SQLite 持久化 | ✅ |
| 操作审计 | ✅ |
| 联系方式查看/复制 | ✅ |

### 简历输入

支持：`.json`、`.txt`、`.md`、`.docx`、`.pdf`。

保护限制：

- 单文件最大 12 MB；
- 单次最多 100 份；
- DOCX 解压大小限制；
- 提取文本长度限制；
- 文件名基础化处理；
- PDF 优先使用 `pypdf`，并保留基础回退解析。

**扫描版 PDF 暂不支持 OCR。**

### AI 评分

模型不能直接决定最终总分：

- 按岗位硬性要求和可配置维度分析；
- 正分维度必须返回简历证据；
- 无证据的正分本地强制归零；
- 硬性要求标记 `met` 但无证据时改为 `unclear`；
- 必需条件 `missing / unclear` 时强制进入人工复核；
- 本地重新计算 0–100 分；
- 输出证据覆盖率、优势、风险和建议追问。

### 候选人管理

候选人详情可查看匹配分、推荐等级、评分维度、简历证据、优势、风险、建议追问、AI 摘要、人工状态、备注，以及本地保存的电话/邮箱/微信/QQ。

招聘阶段：

```text
new → shortlisted → interview → hold → hired / rejected
```

同一候选人更新简历时可以保留评估历史，排行榜只使用最新版本。

### AI 回复草稿

支持追问信息、面试邀请、岗位澄清、收到简历确认和婉拒草稿。回复链路带本地安全扫描，用于提示受保护属性询问、确定录用承诺、联系方式异常泄露和异常长回复。

**所有回复只生成草稿，不自动发送。**

---

## 🔐 数据与模型隔离

招聘工作台把“HR 在本机需要的数据”和“允许发送给 AI 的决策数据”分开处理。

### 本地保留

为了人工联系候选人，本机可以保存姓名、手机号、邮箱、微信、QQ、人工粘贴的聊天原文、招聘阶段和人工备注。

身份证号等非约面所需的身份号码会从结构化字段和自由文本中移除。

### 模型输入

AI 评分和回复生成使用单独安全副本。发送模型前会移除或替换：

- 姓名；
- 手机、邮箱、微信、QQ；
- 身份证号；
- 婚姻状况；
- 年龄和出生日期；
- 性别；
- 民族、国籍、政治面貌等受保护属性。

常见自由文本形式如：

```text
31岁 | 男 | 已婚 | 手机 138... | 微信 abc...
```

同样会在模型请求前处理。候选人稳定性应依据任职时长、工作切换频率、履历空档、项目持续时间和职责连续性等岗位相关证据。

详细说明：[招聘联系人数据处理](docs/recruiter-contact-handling.md) · [数据生命周期](docs/recruiter-data-lifecycle.md)

---

## 👔 BOSS 招聘者接入与平台边界

默认 Assisted Mode 聚焦本地辅助和低风险能力。需要处理候选人数据时，Research Mode 只用于当前实现明确支持、用户已获授权的读取链路。

敏感平台命令（例如 `batch-greet`、apply、候选人消息发送等）默认受策略控制；命中边界会返回 `COMPLIANCE_BLOCKED`。不要把 CDP、浏览器或 Bridge 当成风控绕过机制，出现验证码、账号异常或平台拦截时应停止自动化重试并回到官方页面处理。

完整边界：[平台风险说明](docs/platform-risk.md)。

### 平台兼容层

CLI 全局平台入口：

```text
--platform zhipin|zhilian|qiancheng
```

- BOSS 直聘：`zhipin`
- 智联招聘：`zhilian`
- 前程无忧 / 51job (`qiancheng`)：当前仅注册占位能力
- `QianchengPlatform (51job 占位适配器，统一返回 NOT_SUPPORTED)`

实际能力请以 [Capability Matrix](docs/capability-matrix.md) 和 `boss schema --format native` 为准。

---

## ⚙️ 配置

日常招聘配置优先在 Web 的 **系统设置** 页面完成，包括 AI Provider、模型、Base URL、API Key、运行模式和 BOSS 登录。

CLI 兼容入口：

```bash
boss config list
boss ai config --provider deepseek --model deepseek-chat --api-key "$DEEPSEEK_API_KEY"
boss doctor
boss status
```

API Key 使用项目已有加密存储机制保存到本地数据目录。

---

## 🧩 保留的 CLI / Agent / MCP 能力

Web 工作台是新增主入口，但没有删除原项目能力。开发者和 Agent 仍可以使用 CLI、JSON 信封、Schema、MCP、本地 shortlist、简历管理和求职辅助能力。

招聘 AI CLI：

```text
boss hr ai configure
boss hr ai jobs
boss hr ai evaluate
boss hr ai evaluate-geek
boss hr ai screen
boss hr ai screen-applications
boss hr ai rank
boss hr ai report
boss hr ai mark
boss hr ai reply
```

能力真源：

```bash
boss schema --format native
```

Agent 文档：[Agent Quickstart](docs/agent-quickstart.md) · [Capability Matrix](docs/capability-matrix.md)。

### MCP

```bash
pip install -e '.[mcp]'
boss-mcp --transport stdio
```

MCP 同样遵循默认低风险能力边界，敏感动作不会因为从 MCP 调用就自动开放。

### Browser Bridge 高级诊断

Bridge 是兼容和诊断通道，不是绕过风控的手段。启动本地 daemon：

```bash
python -m boss_agent_cli.bridge.daemon --serve
```

常见诊断组件/能力名：

```text
bridge_daemon
bridge_extension
bridge_protocol
bridge_workspace
bridge_exec
bridge_fetch
bridge_navigate
```

当 Bridge、CDP 或浏览器遇到平台风控，应停止自动化重试并转到官方页面。更多说明见 [平台风险说明](docs/platform-risk.md) 和 [快速开始](docs/getting-started.md)。

---

## 💾 本地数据与生命周期

原生启动默认数据目录：

```text
~/.boss-agent/
```

招聘数据主要位于：

```text
~/.boss-agent/recruiter-ai/
├── jobs/
├── evaluations/
├── replies/
├── web_tasks.db
└── audit.jsonl
```

后台任务使用 SQLite；服务异常退出后，未完成任务会被标记为 `TASK_INTERRUPTED`。删除候选人时同步清理其评估版本、关联草稿和任务历史引用；删除岗位会级联清理该岗位的本地招聘数据。运行中的关联筛选任务会阻止并发删除。

Docker 使用 `boss-recruiter-data` named volume。删除容器并保留数据：

```bash
docker compose -f docker-compose.recruiter.yml down
```

永久删除 Docker 招聘数据：

```bash
docker compose -f docker-compose.recruiter.yml down -v
```

---

## 🐳 Docker 安全默认值

招聘 Web 使用 `Dockerfile.recruiter-web` 和 `docker-compose.recruiter.yml`：

- 容器内监听 8765 供 Docker 转发；
- 宿主机只发布 `127.0.0.1:<port>`；
- 容器非 root 运行；
- Web 服务启动时生成随机 API Token；
- API 校验 Token；
- 请求校验 `Host` / `Origin`；
- 响应包含 CSP、X-Frame-Options、Referrer-Policy、Permissions-Policy 等安全头；
- 数据卷持久化。

日志：

```bash
docker compose -f docker-compose.recruiter.yml logs -f recruiter-web
```

---

## 🏗️ 技术架构

```text
Browser
  ↓
Recruiter Web SPA
  ↓ localhost JSON API + token
RecruiterWebController
  ├─ Job / Rubric
  ├─ Resume parser
  ├─ Recruiter AI evaluation
  ├─ Reply drafting + safety scan
  ├─ RecruiterAIStore
  ├─ AuditLog
  └─ TaskManager (SQLite)
        ↓
  Local files / guarded recruiter adapter

AI path:
local resume + recruiter contacts
  → model-safe copy
  → evidence-backed LLM evaluation
  → local score recomputation
  → human review
```

| 层 | 技术 |
| --- | --- |
| Python | >= 3.10 |
| CLI | Click |
| Web | 原生 HTML/CSS/JavaScript，无前端构建步骤 |
| HTTP | `httpx` + 本地 `ThreadingHTTPServer` |
| 浏览器 | Patchright / Chrome CDP / Browser Bridge |
| 存储 | JSON + SQLite WAL |
| 加密 | `cryptography` / Fernet |
| AI | OpenAI-compatible Provider 体系 |
| PDF | `pypdf` 优先 + 基础回退 |
| 测试 | pytest / Ruff / mypy / Docker smoke |

---

## 🧪 开发与质量门禁

```bash
git clone https://github.com/zerlinpi/boss-agent-cli.git
cd boss-agent-cli
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/boss_agent_cli
```

离线质量门禁：

```bash
uv run python scripts/quality_baseline.py
BOSS_SMOKE_DRY_RUN=1 uv run python scripts/smoke_p0.py
uv run python evals/run_eval.py --mode fixture
```

CI 覆盖 Python 3.10–3.14、pytest/coverage、compileall、Ruff、mypy、CLI/MCP Docker、MCP stdio 初始化、招聘 Web Docker 构建、Compose 配置、非 root 检查和 Web 容器健康检查。

---

## 🔧 排障

### Windows 一键启动失败

优先查看启动窗口最后一条错误。常见原因是企业设备禁用 `winget`、依赖下载无网络、Python 安装被终端安全策略阻止或 8765 端口被占用。

### BOSS 登录提示浏览器内核缺失

```bash
patchright install chromium
```

Windows 一键启动会自动尝试该步骤。

### Docker 端口占用

```bash
BOSS_WEB_PORT=9000 docker compose -f docker-compose.recruiter.yml up -d --build
```

Windows Docker 启动器会拒绝 0、65536 和非整数端口。

### PDF 无法读取

先确认 PDF 中的文字可以被鼠标选中复制；扫描图片 PDF 当前没有 OCR。

### AI 评分偏低或进入人工复核

检查评分维度是否缺少简历证据，或必需硬性条件是否为 `missing / unclear`。这是证据门禁的预期行为。

更多： [快速开始](docs/getting-started.md) · [排障指南](docs/troubleshooting.md) · [平台风险](docs/platform-risk.md)。

---

## ⚠️ 已知边界

- Web 工作台当前主要面向本地单用户，暂未实现中心化多租户/RBAC；
- 扫描版 PDF 暂无 OCR；
- Docker 中的 BOSS 浏览器登录不如 Windows 原生环境直接；
- 平台页面、端点和风控策略可能变化；
- 不承诺平台私有接口长期稳定；
- AI 输出必须由招聘人员复核；
- 本地保存候选人联系方式时，使用者仍需负责访问控制、保留期限和合法使用。

---

## 🤝 上游、贡献与许可证

上游项目：[can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli)。感谢原作者与贡献者提供 CLI、平台适配、认证、AI、MCP 与工程基础。

当前 fork：[zerlinpi/boss-agent-cli](https://github.com/zerlinpi/boss-agent-cli) · [Issues](https://github.com/zerlinpi/boss-agent-cli/issues) · [Pull Requests](https://github.com/zerlinpi/boss-agent-cli/pulls)

许可证：[MIT](LICENSE)。使用本项目时请遵守相关法律法规、候选人隐私要求以及招聘平台适用协议和规则。
