<div align="center">

<img src="docs/assets/logo.svg" width="112" alt="boss-agent-cli logo">

# BOSS Recruit AI / boss-agent-cli

**本地招聘 AI 工作台：岗位画像 → 简历解析 → 证据化评分 → 候选人排序 → Kanban 流转 → 回复草稿 → 人工联系。**

同时保留原 `boss-agent-cli` 的 CLI、AI Agent、MCP 与求职者辅助能力。

[![CI](https://github.com/zerlinpi/boss-agent-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/zerlinpi/boss-agent-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?logo=python&logoColor=white&style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-one--click-0078D4?logo=windows&logoColor=white&style=flat-square)](#windows-一键启动推荐)
[![Docker](https://img.shields.io/badge/Docker-one--click-2496ED?logo=docker&logoColor=white&style=flat-square)](#docker-一键启动)

[快速开始](#-最快启动) · [招聘工作流](#-招聘工作流) · [功能](#-主要能力) · [数据与隐私](#-数据与模型隔离) · [Docker](#docker-一键启动) · [CLI / MCP](#-保留的-cli--agent--mcp-能力) · [开发](#-开发与质量门禁)

</div>

> [!NOTE]
> 这是基于 [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) 的招聘 AI 工作台增强版本。原项目作者、MIT 许可证及其 CLI / MCP 架构均保留；当前 fork 的产品入口、Web 工作台、一键启动和招聘 AI 能力由本仓库继续维护。

> [!IMPORTANT]
> 本项目定位为**招聘 Copilot / 本地招聘工作台**，不是无人值守招聘机器人。AI 只提供辅助评分、排序和沟通草稿；不会自动决定录用/淘汰，也不会自动发送 BOSS 消息。使用平台数据时应遵守适用法律、隐私要求和平台规则；命中风控后应停止自动化访问并回到官方页面处理。

---

## 🚀 最快启动

### Windows 一键启动（推荐）

从 GitHub 下载 ZIP 或拉取 `master` 后，直接双击：

```text
start-recruiter-web.bat
```

第一次启动会自动：

1. 查找 Python 3.10–3.14；
2. 如果没有 Python，尝试通过 Windows `winget` 安装 Python 3.12；
3. 创建项目独立 `.venv`；
4. 安装/更新项目依赖和 PDF 解析依赖；
5. 检查并安装 Patchright Chromium 浏览器内核；
6. 启动本地 Web 服务；
7. 自动打开浏览器。

默认地址：

```text
http://127.0.0.1:8765/
```

关闭启动窗口即可停止本地服务。

> 已有 `.venv` 损坏或 Python 版本过旧时，启动器会自动重建。Chromium 下载失败不会阻止纯本地简历筛选，但 BOSS 浏览器登录可能需要重新安装 Chromium 或使用本机 Chrome。

### Docker 一键启动

Windows + Docker Desktop 可以直接双击：

```text
start-recruiter-docker.bat
```

停止：

```text
stop-recruiter-docker.bat
```

macOS / Linux / 服务器可直接执行：

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

> Docker 最适合本地文件筛选、候选人管理和 AI 工作流。BOSS 登录依赖真实浏览器环境，Windows 原生启动体验更完整；Docker 可通过 `BOSS_CDP_URL=http://host.docker.internal:9222` 连接用户主动启动的宿主机 Chrome 调试端口。

---

## 🎯 招聘工作流

```text
岗位 JD
   ↓
AI 岗位画像 / 可配置评分规则
   ↓
┌────────────────────┬────────────────────┐
│ 本地 PDF/DOCX/TXT  │ BOSS 授权范围候选人 │
└────────────────────┴────────────────────┘
   ↓
简历标准化 + 联系方式本地提取
   ↓
模型安全副本（身份/敏感属性隔离）
   ↓
证据化维度评分 + 本地重算总分
   ↓
候选人排名 / 横向对比 / 风险与追问
   ↓
Kanban：新候选人 → 入围 → 面试 → 待定 → 录用/不合适
   ↓
AI 回复草稿 → 人工审核 → 人工联系候选人
```

### 典型使用步骤

1. 在 **系统设置** 配置 AI；
2. 创建岗位并粘贴 JD；
3. 点击 **AI 分析岗位** 自动生成评分维度与硬性要求；
4. 上传简历，或在明确授权的 Research Mode 下读取 BOSS 投递候选人；
5. 等待后台任务完成；
6. 在 **招聘概览** 查看 Top 候选人和漏斗；
7. 在 **候选人工作台** 使用列表/Kanban、搜索、排序、批量流转和候选人对比；
8. 打开候选人详情查看证据、风险、联系人和建议追问；
9. 生成回复草稿，人工审核后再通过官方渠道联系候选人。

---

## 🌟 主要能力

### 招聘控制台

| 能力 | 当前状态 |
| --- | --- |
| 图形 Web 界面 | ✅ |
| Windows 双击启动 | ✅ |
| Docker Compose 一键启动 | ✅ |
| 招聘 Dashboard | ✅ |
| 多岗位配置 | ✅ |
| AI 分析 JD | ✅ |
| 自定义评分规则 | ✅ |
| 候选人列表 | ✅ |
| Kanban 招聘阶段 | ✅ |
| 拖拽流转 | ✅ |
| 批量状态更新 | ✅ |
| 搜索 / 过滤 / 排序 | ✅ |
| CSV 导出 | ✅ |
| 2–4 人横向比较 | ✅ |
| 操作审计 | ✅ |
| 后台任务历史 | ✅ |
| 重启后任务记录恢复 | ✅ |

### 简历输入

支持：

- `.json`
- `.txt`
- `.md`
- `.docx`
- `.pdf`

上传防护：

- 单文件最大 12 MB；
- 单次最多 100 份；
- DOCX 解压大小限制；
- 提取文本长度限制；
- 文件名基础化处理；
- PDF 优先使用 `pypdf` 提取文本。

**暂不支持扫描版 PDF OCR。** 扫描件需要先转换为可复制文字的 PDF，或转成 DOCX/TXT。

### AI 评分

AI 不直接拥有最终总分决定权。

评分流程包含：

- 岗位硬性要求检查；
- 可配置维度及权重；
- 模型语义判断；
- 每个正分维度必须返回简历证据；
- 没有证据的正分在本地强制归零；
- 硬性要求声称 `met` 但没有证据时改为 `unclear`；
- 必需条件 `missing / unclear` 时强制进入人工复核；
- 本地重新计算 0–100 总分；
- 输出证据覆盖率、优势、风险和建议追问。

默认评分维度包括技能、相关经验、项目证据、职责匹配、行业匹配和成果证据，也可以按岗位修改。

### 候选人管理

候选人详情可以查看：

- 综合匹配分；
- 推荐等级；
- 评分维度；
- 简历证据；
- 优势；
- 风险与待确认项；
- 建议追问；
- AI 摘要；
- 人工状态和备注；
- 电话、邮箱、微信、QQ 等本地联系人信息。

候选人阶段：

```text
new → shortlisted → interview → hold → hired / rejected
```

同一候选人更新简历时会生成新评估版本，但排行榜只使用最新版本。

### AI 回复草稿

支持生成：

- 追问信息；
- 面试邀请；
- 岗位澄清；
- 收到简历确认；
- 婉拒草稿。

回复链路有本地安全扫描，可提示：

- 受保护属性询问；
- 确定录用承诺；
- 联系方式异常泄露；
- 异常长回复。

**草稿不会自动发送。**

---

## 🔐 数据与模型隔离

招聘工作台将“HR 在本机需要使用的数据”和“允许发送给 AI 的评分数据”分开处理。

### 本地保留

为了实际联系候选人，本机可以保存：

- 姓名；
- 手机号；
- 邮箱；
- 微信；
- QQ；
- 人工粘贴的聊天原文；
- 招聘阶段和人工备注。

身份证号等非约面所需的身份号码会从结构化字段和自由文本中移除。

### 发送模型前隔离

AI 评分与回复生成使用单独的安全副本。模型输入会移除或替换：

- 姓名；
- 手机、邮箱、微信、QQ；
- 身份证号；
- 婚姻状况；
- 年龄和出生日期；
- 性别；
- 民族、国籍、政治面貌等受保护属性。

常见自由文本格式，例如：

```text
31岁 | 男 | 已婚 | 手机 138... | 微信 abc...
```

也会在发送模型前处理。

候选人“稳定性”应依据岗位相关履历证据，例如任职时长、工作切换频率、履历空档和项目持续时间，而不是婚姻、年龄或性别。

详细说明：[`docs/recruiter-contact-handling.md`](docs/recruiter-contact-handling.md)

---

## 🧠 AI 配置

Web 界面可直接配置 AI，无需编辑配置文件。

支持项目现有 AI Provider 体系及 OpenAI-compatible API，包括常见的：

- OpenAI-compatible 服务；
- DeepSeek；
- Qwen / 通义千问；
- GLM / 智谱；
- Ollama；
- vLLM；
- 其他自定义兼容端点。

API Key 使用项目原有加密存储机制保存在本地数据目录。

也可以继续使用 CLI 配置：

```bash
boss ai config --provider deepseek --model deepseek-chat --api-key "$DEEPSEEK_API_KEY"
```

---

## 👔 BOSS 招聘者接入

### Assisted Mode

默认模式。优先本地处理和低风险辅助，敏感平台动作保持受限。

### Research Mode

在明确获得候选人数据处理授权并理解平台风险后，Web 控制台可切换 Research Mode，用于当前实现支持的招聘者读取链路，例如投递候选人和在线简历筛选。

项目不会提供：

- 验证码绕过；
- 风控绕过；
- 反检测规避策略；
- 无人值守批量触达；
- 自动淘汰/录用；
- 自动向候选人发送消息。

当平台出现风控提示、验证码、账号异常或能力不可用时，应停止自动化重试并在官方页面人工处理。

---

## 💾 本地数据与生命周期

原生启动默认数据目录：

```text
~/.boss-agent/
```

招聘工作台数据位于：

```text
~/.boss-agent/recruiter-ai/
```

主要数据：

```text
recruiter-ai/
├── jobs/              # 岗位配置
├── evaluations/       # 候选人评估版本
├── replies/           # 回复草稿与本地聊天上下文
├── web_tasks.db       # Web 后台任务
└── audit.jsonl        # 操作审计
```

后台任务使用 SQLite，并启用 WAL、busy timeout 等并发设置。服务异常退出后，未完成任务会被标记为 `TASK_INTERRUPTED`，不会伪装成成功。

永久删除候选人时会同步清理其评估版本、关联草稿以及任务历史中的候选人引用；删除岗位会级联清理该岗位的本地招聘数据。运行中的关联筛选任务会阻止并发删除。

详细说明：[`docs/recruiter-data-lifecycle.md`](docs/recruiter-data-lifecycle.md)

---

## 🐳 Docker 说明

招聘 Web 使用独立镜像：

```text
Dockerfile.recruiter-web
```

Compose：

```text
docker-compose.recruiter.yml
```

安全默认值：

- 容器内服务监听 `0.0.0.0:8765` 供 Docker 转发；
- 宿主机只发布 `127.0.0.1:<port>`；
- 容器使用非 root 用户；
- 每次 Web 服务启动生成随机 API Token；
- Web API 校验 Token；
- 页面请求校验 `Host` / `Origin`；
- 带 CSP、X-Frame-Options、Referrer-Policy、Permissions-Policy 等响应头；
- 招聘数据使用 named volume 持久化。

查看日志：

```bash
docker compose -f docker-compose.recruiter.yml logs -f recruiter-web
```

停止但保留数据：

```bash
docker compose -f docker-compose.recruiter.yml down
```

删除容器和招聘数据卷：

```bash
docker compose -f docker-compose.recruiter.yml down -v
```

> `down -v` 会永久删除 Docker 中的招聘数据，请谨慎使用。

---

## 🧩 保留的 CLI / Agent / MCP 能力

当前 fork 没有移除原项目能力。Web 工作台是新增主入口，CLI 仍可用于开发、Agent 编排和诊断。

常用命令：

```bash
boss doctor
boss login
boss status
boss schema
boss hr jobs list
boss hr ai jobs
boss hr ai report --job-key <job_key>
```

招聘 AI CLI 子命令：

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

求职者侧原有的搜索、职位详情、本地 shortlist、简历管理、AI 简历辅助、Agent、MCP 等能力仍保留。完整能力以：

```bash
boss schema --format native
```

为准，不建议在外部 Agent 中硬编码命令数量。

### MCP

安装 MCP 额外依赖：

```bash
pip install -e '.[mcp]'
```

启动：

```bash
boss-mcp --transport stdio
```

MCP 默认仍遵循项目低风险能力边界；敏感平台动作不会因为从 MCP 调用就自动放开。

---

## 🏗️ 架构

```text
Browser
  │
  ▼
Recruiter Web SPA
  │  localhost JSON API + session token
  ▼
RecruiterWebController
  ├── Job / Rubric service
  ├── Resume document parser
  ├── Recruiter AI evaluation
  ├── Reply drafting + safety scan
  ├── RecruiterAIStore
  ├── AuditLog
  └── TaskManager (SQLite)
         │
         ├── Local files
         └── BOSS Recruiter adapter (authorized / guarded)

AI path:
Local resume with recruiter contacts
  → model-safe copy
  → evidence-backed LLM evaluation
  → local score recomputation
  → human review
```

核心技术：

| 层 | 技术 |
| --- | --- |
| 语言 | Python >= 3.10 |
| CLI | Click |
| Web | 原生 HTML / CSS / JavaScript，零前端构建步骤 |
| HTTP | `httpx` + 本地 `ThreadingHTTPServer` |
| 浏览器 | Patchright / Chrome CDP / Browser Bridge |
| 本地存储 | JSON + SQLite WAL |
| 加密 | `cryptography` / Fernet |
| AI | OpenAI-compatible Provider 体系 |
| PDF | `pypdf` 优先 + 基础回退解析 |
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

CI 会检查：

- Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14；
- pytest + coverage；
- Python compileall；
- Ruff；
- mypy；
- CLI/MCP Docker 镜像；
- MCP stdio 初始化；
- 招聘 Web Docker 镜像；
- Recruiter Compose 配置；
- Web 容器非 root；
- Web 首页健康检查。

---

## 🔧 排障

### Windows 双击后立即失败

先看启动窗口中的最后一条错误。常见原因：

- 企业电脑禁用 `winget`；
- Python 安装被安全软件阻止；
- 首次依赖下载没有网络；
- 8765 端口已被占用。

已有 Python 3.10+ 时启动器不会强制安装新 Python。

### BOSS 登录提示浏览器内核缺失

Windows 一键启动会执行：

```bash
patchright install chromium
```

也可以手动运行同一命令。Patchright 官方 Python 包同样要求单独安装 Chromium 浏览器驱动。

### Docker 端口被占用

```bash
BOSS_WEB_PORT=9000 docker compose -f docker-compose.recruiter.yml up -d --build
```

Windows PowerShell / BAT 启动器会拒绝 `0`、`65536` 或非整数端口。

### PDF 无法读取

先确认 PDF 中的文字可以被鼠标选中复制。扫描图片 PDF 当前没有 OCR。

### AI 评分为 0 或进入人工复核

检查候选人的评分维度是否缺少简历证据，或必需硬性条件是否为 `missing / unclear`。这是证据门禁的预期行为，而不是简单的模型失败。

更多原 CLI 排障资料：[`docs/troubleshooting.md`](docs/troubleshooting.md)

---

## ⚠️ 已知边界

- 当前 Web 工作台主要面向本地单用户；暂未实现中心化多租户/RBAC；
- 扫描版 PDF 暂无 OCR；
- Docker 中的 BOSS 浏览器登录不如 Windows 原生环境直接；
- 平台页面、端点和风控策略可能变化；
- 本项目不承诺平台私有接口长期稳定；
- AI 输出必须由招聘人员复核；
- 本地保存候选人联系方式时，使用者仍需承担访问控制、保留期限和合法使用责任。

---

## 🤝 上游、贡献与许可证

本仓库基于：

- [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli)

感谢原项目作者和贡献者提供 CLI、平台适配、认证、MCP、AI 与工程基础。

当前 fork 的 Issue / PR：

- [Issues](https://github.com/zerlinpi/boss-agent-cli/issues)
- [Pull Requests](https://github.com/zerlinpi/boss-agent-cli/pulls)

许可证：[`MIT`](LICENSE)

使用本项目时请遵守相关法律法规、候选人隐私要求以及招聘平台的适用协议和规则。项目不为未经授权的数据处理、账号异常、平台限制或不当自动化承担责任。
