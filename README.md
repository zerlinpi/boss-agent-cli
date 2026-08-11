<div align="center">

<img src="docs/assets/logo.svg" width="112" alt="BOSS Recruit AI logo">

# BOSS Recruit AI

### 基于 `boss-agent-cli` 的本地 AI 招聘工作台

**岗位画像 → 简历解析 → 证据化评分 → 候选人排序 → Kanban 流转 → AI 回复草稿 → 人工联系**

[![CI](https://github.com/zerlinpi/boss-agent-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/zerlinpi/boss-agent-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?logo=python&logoColor=white&style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/zerlinpi/boss-agent-cli/pulls)

[Windows 一键启动](#-windows-一键启动推荐) · [Docker](#-docker-一键启动) · [功能](#-当前功能) · [数据与模型隔离](#-数据与模型隔离) · [开发](#-开发与质量门禁) · [English](README.en.md)

</div>

> [!NOTE]
> 本仓库由 [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) fork 并持续开发。原项目的 CLI、认证、平台适配、AI、MCP 等基础能力和 MIT 许可证继续保留；本 fork 的招聘 AI Web 工作台、一键启动、招聘数据流和相关测试由 `zerlinpi/boss-agent-cli` 维护。

> [!IMPORTANT]
> 这是 **Recruiting Copilot / 本地招聘工作台**，不是无人值守招聘机器人。AI 负责辅助分析、排序和生成回复草稿；最终面试、录用、淘汰以及候选人消息发送仍由招聘人员确认。平台出现验证码、风险控制、账号异常或权限阻断时，不应自动绕过。

---

## 🚀 30 秒开始使用

### 🪟 Windows 一键启动（推荐）

下载仓库 ZIP 并解压，或拉取 `master`：

```bash
git clone https://github.com/zerlinpi/boss-agent-cli.git
cd boss-agent-cli
```

然后**双击仓库根目录**：

```text
start-recruiter-web.bat
```

第一次启动会自动：

1. 查找 Python 3.10–3.14；
2. 没有可用 Python 时尝试通过 `winget` 安装 Python 3.12；
3. 创建或修复项目独立 `.venv`；
4. 安装/更新项目依赖与 `pypdf`；
5. 检查 Patchright 并尝试安装 Chromium；
6. 启动本地招聘 Web 服务；
7. 自动打开浏览器。

默认地址：

```text
http://127.0.0.1:8765/
```

关闭启动窗口即可停止服务。

> Chromium 下载失败不会阻止本地 PDF/DOCX/JSON 简历工作流，但 BOSS 浏览器登录可能需要修复 Chromium 或使用已安装的 Chrome/CDP。

### 🐳 Docker 一键启动

Windows + Docker Desktop：

```text
双击 start-recruiter-docker.bat
```

停止：

```text
双击 stop-recruiter-docker.bat
```

macOS / Linux：

```bash
docker compose -f docker-compose.recruiter.yml up -d --build
```

停止：

```bash
docker compose -f docker-compose.recruiter.yml down
```

默认只发布到本机：

```text
127.0.0.1:8765
```

自定义端口：

```bash
BOSS_WEB_PORT=9000 docker compose -f docker-compose.recruiter.yml up -d --build
```

Docker 数据保存在命名卷：

```text
boss-recruiter-data
```

删除容器不会删除招聘数据；只有执行：

```bash
docker compose -f docker-compose.recruiter.yml down -v
```

才会同时删除该 Docker 数据卷。

### 开发者手动启动

安装当前仓库后：

```bash
pip install -e .
boss-recruit-web
```

不自动打开浏览器：

```bash
boss-recruit-web --no-open
```

---

## 🎯 最终工作流

```text
岗位 JD
  │
  ▼
AI 岗位画像 + 可配置评分规则
  │
  ├── 本地 JSON / TXT / Markdown / DOCX / PDF
  └── 当前实现和授权范围内的 BOSS 招聘者数据
  │
  ▼
简历标准化 + 本地联系人提取
  │
  ├── 本地 HR 数据副本
  └── 模型安全副本
          │
          ▼
    证据化 AI 评分
          │
          ▼
    本地重算 0–100 分
          │
          ▼
候选人排名 / 对比 / 风险 / 追问
  │
  ▼
Kanban：新候选人 → 入围 → 面试 → 待定 → 录用 / 不合适
  │
  ▼
AI 回复草稿 → 本地安全扫描 → 人工审核 → 人工联系
```

---

## ✨ 当前功能

### 招聘 Dashboard

- 候选人总量、推荐面试、人工复核、面试阶段等指标；
- 招聘漏斗；
- 评分分布；
- 最近 7 天处理量；
- Top 候选人；
- AI、登录、运行模式状态；
- 旧版本 `Z / +08:00 / 无时区` 时间戳按实际 UTC 时间排序；
- 多岗位首页引导只扫描一次评估目录，再按岗位在请求内过滤，避免岗位数量放大磁盘读取；
- 岗位 JD 或评分规则变化后，旧评分会退出当前排名/统计/CSV，并显示待重新筛选数量；历史评估文件仍保留用于审计。

### 岗位配置

- 多岗位管理；
- 粘贴完整 JD；
- AI 自动生成岗位画像；
- 自动生成硬性要求和评分维度；
- 自定义评分权重；
- 自定义推荐阈值；
- 可关联 BOSS 职位 ID。

评分规则是本地强校验契约，而不是仅靠提示词约束。维度、硬性要求、`instructions`，以及 AI 岗位画像中的标题、画像摘要和建议面试问题，一旦包含年龄、性别、婚育、民族/种族、宗教、健康/残障、政治身份等个人属性，会直接拒绝保存或进入评分链路。`90后 / 年轻优先 / under 30` 等年龄代理条件同样会被拒绝。

### 简历上传与解析

支持：

```text
.json
.txt
.md
.docx
.pdf
```

当前限制：

- 单文件最大 12 MB；
- 单次最多 100 份，解码后总量最大 40 MB；
- 浏览器和本地 API 使用同一批次上限，超限会在文件解码/解析前拒绝；
- JSON 简历最大 500000 字符；
- DOCX 解压后内容及内部条目数有限额；
- 提取文本有限长；
- PDF 最多 100 页，优先使用 `pypdf` 并保留基础回退解析；
- **扫描图片 PDF 暂不支持 OCR**。

浏览器会按文件顺序读取，而不是同时把全部文件 `Promise.all` 进内存，以降低大批量上传的瞬时内存峰值。

### AI 候选人评分

评分不是简单询问模型“这个人合不合适”。当前流程包含确定性门禁：

- 每个正分维度必须提供简历证据；
- 无证据的正分会在本地归零；
- 硬性要求标为 `met` 却没有证据时改为 `unclear`；
- 必需条件为 `missing / unclear` 时强制进入人工复核；
- 模型提供维度分，本地代码重新计算总分；
- 评分规则的维度分值必须是有限正整数；
- 推荐阈值必须是 0–100 的有限整数并保持正确顺序；
- `NaN / Infinity` 等非有限模型输出不会进入有效排名；
- 模型返回的维度名会做大小写、camelCase、空格和标点归一，例如 `required_skills / RequiredSkills / Required Skills / required-skills` 可对应同一标准维度；
- 中文自定义维度名，例如 `后端经验 / 项目复杂度`，会保留 Unicode 文本并正常匹配；
- 硬性要求会做大小写和多余空白归一，例如配置 `Java`、模型返回 `  java  ` 时不会误判为缺失；
- 模型自行增加未配置硬条件时不会进入正式结果；
- 模型输出的 evidence、concerns、next questions、summary 等还会经过本地安全扫描；受保护属性或联系方式内容会被移除，相关证据不能继续支撑正分，并强制进入 `manual_review`；
- 输出仍使用本地配置中的标准维度/硬性要求名称；
- 输出证据覆盖率、优势、风险和建议追问。

默认评分维度包括：

- 必需技能；
- 相关工作经验；
- 项目证据；
- 职责匹配；
- 行业匹配；
- 量化成果证据。

### 候选人工作台

支持：

- 列表 / Kanban 双视图；
- 排序、搜索、过滤；
- 拖拽招聘阶段；
- 批量状态更新；
- 2–4 人横向比较；
- 候选人详细评分证据；
- 优势、风险、下一步追问；
- 电话、邮箱、微信、QQ 本地查看与复制；
- CSV 导出；
- 候选人当前岗位数据删除，以及岗位级联数据删除。

招聘阶段：

```text
new → shortlisted → interview → hold → hired / rejected
```

人工阶段和人工备注属于**候选人级状态**。简历更新触发新的 AI 评估版本时状态不会自动退回 `new`；即使人工操作来自旧的 evaluation ID，也会同步同一逻辑候选人的所有评估版本，避免旧链接、CLI 与最新 Kanban 出现状态分裂。

删除候选人时只清理该候选人在**当前岗位**下的全部评估版本和关联回复；同一候选人在其他岗位中的记录会保留。删除岗位则仍会级联清理该岗位的候选人评估、回复和关联任务记录。

### 增量筛选

同一候选人会根据：

- 稳定候选人标识；
- 简历指纹；
- 岗位 JD；
- 评分规则指纹；

判断是否发生变化。

本地 CLI 文件优先使用规范化来源路径作为稳定身份；BOSS 候选人优先使用 `geek_id`，再退到其他平台 ID。历史版本在读取时按当前 canonical identity 归组，不要求批量改写旧 JSON。

未变化的候选人默认跳过，避免重复消耗模型调用。**即使 AI 当前未配置，只要本次所有简历都已评估且 JD、简历和评分规则都未变化，增量检查也可以正常完成。**

JD 或评分规则发生变化后，历史评估不会删除，但会被视为 **stale**：

- Web 当前排名、Dashboard 指标、分析和 CSV 会排除 stale 结果；
- 页面显示 `stale_count` 对应的“需要重新筛选”提示；
- 历史候选人详情仍可查看，但会显示 freshness 警告，说明是旧 JD、旧评分规则或已被新版本替代；若已有更新 evaluation，可直接跳到最新版本；
- CLI `rank / report` 对已保存岗位也只展示当前 JD + rubric 的评估；`report` 返回 `stale_count`；
- 没有已保存岗位的 ad-hoc CLI 评估仍保留原来的排名行为；
- 重评后会重新进入当前排名，并继承候选人级人工阶段和备注。

单次 Web 筛选会缓存当前岗位的 latest-candidate 索引，避免每处理一份简历都重新扫描整个评估目录；候选人列表中的排名、报告和分析也在同一请求内共享索引。CLI 批量筛选同样会在当前 Store 生命周期内缓存 latest-candidate 索引，并在外部文件变化或本轮写入后正确失效/更新。

岗位配置读取也使用文件 mtime 可失效缓存；保存、替换或删除岗位 JSON 后会重新加载，避免大批量筛选为每位候选人重复解析同一个岗位文件。

### AI 回复草稿

支持：

- 收到简历确认；
- 信息追问；
- 面试邀请；
- 岗位澄清；
- 婉拒草稿。

回复生成后还会做本地规则扫描，包括：

- 受保护属性询问；
- 确定录用承诺，例如“我们决定录用你 / 欢迎入职”；
- 电话/邮箱/微信/QQ 等联系方式异常暴露；
- 身份证、护照、住宅地址等高风险身份数据暴露；
- 异常长回复。

Web 和 CLI 的批量筛选 `draft_top` 都只会自动为**本轮实际新增/重新评估**的候选人生成草稿，不会因为历史 Top 候选人仍排在前面就重复调用模型或重复读取聊天。

单独生成草稿时必须使用当前候选人的**最新且基于当前 JD/rubric 的 evaluation**。旧 JD、旧评分规则或已经被新版本替代的 evaluation 会被 Web 以 `STALE_EVALUATION` 拒绝；CLI 同样会在解析 AI 配置和调用模型之前拒绝旧 evaluation ID。历史记录仍可查看，但不能直接作为新的 AI 沟通依据。

**系统不会自动发送这些回复。**

---

## 🔐 数据与模型隔离

招聘工作台刻意把“HR 在本机需要查看的数据”和“允许进入模型决策的数据”分成两条通道。

### 本地 HR 通道

本地记录可以保留用于人工招聘流程的信息，例如：

- 候选人姓名；
- 简历原始/结构化业务字段；
- 年龄、性别、婚姻状况等原简历字段（仅供人工查看，不进入 AI 决策输入）；
- 手机号；
- 邮箱；
- 微信；
- QQ；
- 人工粘贴的聊天内容；
- 招聘阶段；
- 人工备注。

为减少不必要的数据留存，以下信息会在本地标准化/持久化边界被移除：

- 连续或常见空格/短横线格式的身份证号；
- 护照号字段及带明确标签的护照号码；
- 家庭住址、现住址、居住地址等住宅详细地址。

电话、邮箱、微信、QQ 等用于人工约面的联系方式可以本地保留；`面试地址` 等招聘流程信息不会因为住宅地址规则被误删。回复记录中的本地聊天也执行同一高风险身份数据清理，而不是重新写回未清洗原文。

### AI 决策通道

调用 AI 时会生成独立的模型安全副本。模型输入会移除或替换：

- 姓名；
- 手机号和座机；
- 邮箱；
- 微信、QQ；
- 身份证号、护照号和住宅详细地址；
- 婚姻状况；
- 年龄和出生日期；
- 性别；
- 民族 / race / ethnicity；
- 国籍；
- 政治面貌；
- 宗教；
- 健康、疾病和残障信息；
- 怀孕、生育和相关状态；
- `年龄限制 / 性别偏好 / 婚姻稳定性 / 90后 / 年轻优先` 等个人属性代理条件。

字段匹配同时覆盖常见：

- `snake_case`；
- `camelCase`；
- 英文别名；
- 中文字段名；
- 自由文本；
- 常见带空格/短横线的身份证格式。

例如：

```text
31岁 | 男 | 已婚 | 中共党员 | 已育一子 | 5年 Java 经验 | 电话 010-12345678 | 微信 abc123
```

进入评分模型前会保留 `5年 Java 经验` 等岗位证据，并隔离其他身份、联系方式和受保护属性。

候选人“稳定性”应依据：

- 每段工作任职时长；
- 工作切换频率；
- 履历空档；
- 项目持续时间；
- 职责连续性；

而不是婚姻、性别、年龄等属性。

更多说明：

- [招聘联系人数据处理](docs/recruiter-contact-handling.md)
- [招聘数据生命周期](docs/recruiter-data-lifecycle.md)

---

## 👔 BOSS 招聘者接入

Web 设置页可以完成 BOSS 登录和运行模式切换。

默认 `assisted` 模式侧重本地辅助和低风险能力。候选人读取链路只应在当前实现支持、账号具备相应权限并明确启用的场景使用。

当前招聘 AI CLI 仍保留：

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

发生以下情况时应停止自动化重试并回到官方页面：

- 验证码；
- 风险控制页面；
- 登录异常；
- 账号限制；
- 权限错误；
- 页面/接口明显变更。

不要将 CDP、Patchright、Bridge 或其他浏览器能力用于规避平台风控。

详细说明：[平台风险边界](docs/platform-risk.md)。

---

## 🤖 AI 配置

优先在 Web 的 **系统设置** 页面配置：

- Provider；
- Model；
- Base URL；
- API Key；
- temperature；
- max tokens。

也保留 CLI：

```bash
boss ai config --provider deepseek --model deepseek-chat --api-key "$DEEPSEEK_API_KEY"
```

系统继续兼容 OpenAI-compatible Provider，也可使用项目已有的 Ollama / vLLM 本地模型配置能力。

API Key 使用项目已有加密存储机制保存在本机数据目录。

AI HTTP 客户端使用进程级惰性共享 `httpx.Client` 复用连接池，批量评分不会为每位候选人重新建立一套 HTTP/TLS 连接。客户端在进程退出时关闭，同时保留现有测试/集成对模块级 `httpx.post` 的 monkeypatch 兼容。

AI 客户端只对明确的瞬时错误做有限重试：`429 / 500 / 502 / 503 / 504`、连接建立失败和连接超时最多尝试 3 次；`400 / 401` 等配置或权限错误不会重试。读取超时也不会自动重试，因为服务端可能已经执行了模型请求，自动重放可能造成重复计费。

---

## 🐳 Docker 与宿主机浏览器

Docker 工作台最适合：

```text
本地简历上传
→ AI 分析
→ 排名
→ Kanban
→ 人才库
→ 回复草稿
```

BOSS 登录涉及真实浏览器环境，Windows 原生启动通常更直接。

Docker 需要连接用户主动开启的宿主机 Chrome CDP 时，可以设置：

```bash
BOSS_CDP_URL=http://host.docker.internal:9222 \
docker compose -f docker-compose.recruiter.yml up -d --build
```

Compose 默认只把容器端口映射到宿主机 `127.0.0.1`，不会默认暴露到局域网或公网。

---

## 💾 本地数据

原生默认数据目录：

```text
~/.boss-agent/
```

招聘工作台主要数据：

```text
~/.boss-agent/recruiter-ai/
├── jobs/
├── evaluations/
├── replies/
├── web_tasks.db
└── audit.jsonl
```

后台任务使用 SQLite：

- WAL；
- `NORMAL` synchronous；
- busy timeout；
- 服务重启后将未完成的 `queued / running` 任务标为 `TASK_INTERRUPTED`；
- 任务横幅支持取消：排队任务会直接取消，运行中任务进入 `cancelling`，等待当前原子操作返回后终结为 `TASK_CANCELLED`；
- 若服务在 `cancelling` 中被重启，该任务会在恢复时终结为 `TASK_CANCELLED`，不会永久占用岗位筛选锁；
- `cancelling` 仍被视为活跃筛选，因此不会出现“点击取消后立即删除岗位、旧线程随后又写回数据”的竞态；
- 删除岗位/候选人与筛选任务提交使用同一临界区，避免“删除检查通过后又插入新筛选任务”的 check-then-delete 竞态；
- `queued / running / cancelling` 活跃任务总数硬限制为 20，超过后 API 返回 `TASK_QUEUE_FULL` / HTTP 429，避免长期运行时无界堆积；
- 线程池在服务关闭竞态中拒绝新任务时，该任务会立即记录为 `TASK_SUBMIT_FAILED`，不会永久停在 `queued`；
- 候选人删除会清理当前岗位内同一 canonical identity 下的历史评估、回复和任务结果引用，包括升级前的旧 key；其他岗位中的同一候选人会保留；
- 岗位删除会级联清理关联招聘记录；
- 有关联筛选任务运行或取消中时会阻止删除。

> 运行中的 Python 线程无法安全强杀一条已经发出的 HTTP/模型请求。取消的语义是“停止继续处理并等待当前调用返回”；当前调用完成后任务不会再变成 `completed`，也不会继续处理下一位候选人。

---

## 🛡️ Web 安全默认值

本地 Web 工作台包含：

- 默认只绑定 `127.0.0.1 / localhost`；
- 启动时随机生成 Web API Token；
- API 请求 Token 校验；
- `Host` / `Origin` 回环地址检查；
- 请求体大小限制；
- 负数/非法 `Content-Length` 拒绝；
- 简历批次解码前 40 MB 服务端门禁；
- 写请求严格类型校验，危险 `_delete` 必须是字面布尔值 `true`；
- 异步筛选/JD 分析的明显结构错误会在进入任务队列前拒绝；
- CSP；
- `X-Frame-Options: DENY`；
- `X-Content-Type-Options: nosniff`；
- `Referrer-Policy: no-referrer`；
- Permissions Policy；
- CSV Formula Injection 防护；
- Docker 非 root 用户；
- Docker Host 端口仅发布到回环地址。

---

## ⚙️ 配置

CLI/Agent 的公开配置真源仍是 `boss config` 与 `boss schema --format native`。跨平台调用可显式选择：

```text
--platform zhipin|zhilian|qiancheng
```

`qiancheng` 当前仍是稳定 `NOT_SUPPORTED` 占位适配器；没有经过 readiness gate 验证的 51job 私有接口不会通过 Web、CLI 或 Browser Bridge 暗中启用。

默认低风险模式下，被策略阻断的敏感动作返回结构化 `COMPLIANCE_BLOCKED`，调用方应停止自动动作并回到官方平台人工处理，而不是切换浏览器/CDP 方式重试。

`boss doctor` 会分别报告浏览器桥扩展与本地桥进程；诊断字段 `bridge_daemon` 表示本地 Bridge daemon 的可达/运行状态。Bridge 只用于用户主动的本地诊断和兼容路径，不得用于规避平台风控。

---

## 🏗️ 技术架构

```text
Browser
  │
  ▼
Recruiter Web SPA
  │ localhost JSON API + token
  ▼
RecruiterWebController
  ├─ Job / Rubric
  ├─ Resume documents
  ├─ Recruiter AI evaluator
  ├─ Candidate ranking
  ├─ Reply drafting + deterministic safety
  ├─ RecruiterAIStore
  ├─ AuditLog
  └─ TaskManager / SQLite
          │
          ├─ Local resume data
          └─ guarded recruiter platform adapter

AI decision path
  │
  ├─ local recruiter copy
  │
  └─ model-safe copy
        ↓
    LLM evidence scoring
        ↓
    local score validation / recomputation
        ↓
    human review
```

| 层 | 当前技术 |
| --- | --- |
| Python | 3.10–3.14 |
| CLI | Click |
| Web UI | 原生 HTML / CSS / JavaScript，无前端构建步骤 |
| HTTP | `ThreadingHTTPServer` + JSON API |
| HTTP Client | httpx connection pool |
| Browser | Patchright / Chrome CDP / Browser Bridge |
| Store | JSON + SQLite WAL |
| Encryption | cryptography / Fernet |
| AI | OpenAI-compatible service abstraction + structural ChatService contract |
| PDF | pypdf + fallback extractor |
| Tests | pytest / Ruff / mypy / Docker smoke |

---

## 🧩 原项目 CLI / Agent / MCP 能力

本 fork 没有删除原 `boss-agent-cli` 能力。开发者仍可使用：

```bash
boss doctor
boss login
boss status
boss schema --format native
boss search "Python"
boss shortlist list
boss ai local --help
boss hr --help
```

MCP：

```bash
pip install -e '.[mcp]'
boss-mcp --transport stdio
```

能力真源始终以：

```bash
boss schema --format native
```

为准，而不是 README 中手写的命令数量。

Agent 文档：

- [Agent Quickstart](docs/agent-quickstart.md)
- [Capability Matrix](docs/capability-matrix.md)
- [Host Examples](docs/agent-hosts.md)

---

## 🧪 开发与质量门禁

推荐开发环境：

```bash
git clone https://github.com/zerlinpi/boss-agent-cli.git
cd boss-agent-cli
uv sync --all-extras
```

全量质量基线：

```bash
uv run python scripts/quality_baseline.py
```

单独执行：

```bash
uv run pytest tests/ -v
uv run ruff check src/ tests/ scripts/
uv run mypy src/boss_agent_cli
```

离线 smoke：

```bash
BOSS_SMOKE_DRY_RUN=1 uv run python scripts/smoke_p0.py
uv run python evals/run_eval.py --mode fixture
```

当前 CI 工作流覆盖：

- Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14；
- pytest + coverage；
- compileall；
- Ruff；
- mypy；
- CLI/MCP Docker 镜像；
- MCP stdio handshake；
- Recruiter Web Docker 镜像；
- Recruiter Compose 配置验证；
- 非 root 容器检查；
- Recruiter Web HTTP / healthcheck smoke。

---

## 🔧 常见问题

### Windows 双击后提示 Python 不存在

启动器会优先尝试 `py` / `python`，没有可用 Python 时使用 `winget` 安装 Python 3.12。企业电脑禁用 `winget` 时，需要手动安装 Python 3.10–3.14。

### BOSS 登录提示浏览器内核缺失

Windows 一键启动会自动尝试：

```bash
patchright install chromium
```

也可以在项目虚拟环境中手动执行。

### 8765 端口已占用

Docker：

```bash
BOSS_WEB_PORT=9000 docker compose -f docker-compose.recruiter.yml up -d --build
```

Windows Docker 启动器会拒绝非法端口值。

### PDF 无法解析

确认 PDF 中的文字能被鼠标选择和复制。纯图片/扫描版 PDF 当前没有 OCR。

### AI 评分突然变低

先检查：

- 评分维度是否有简历证据；
- 硬性要求是否被判为 `missing / unclear`；
- JD 或评分规则是否刚修改；
- 简历是否实际提供了岗位要求的信息；
- 模型输出是否因为包含受保护属性/联系方式而被本地安全层移除证据并降级为人工复核。

“无证据不加分”是当前设计，而不是异常。

### 修改 JD 后为什么候选人从排名里消失

当前评分只对生成它时的 JD 和 rubric 有效。修改岗位 JD 或评分规则后，旧评估会保留为历史审计记录，但不会继续参与当前排名、统计或 CSV。Web 会显示需要重新筛选的候选人数；历史详情会标明它为什么过期，并在已经存在新 evaluation 时提供“打开最新评估”。重新筛选后，新评估会重新进入排名并继承人工阶段/备注。

### 为什么旧 evaluation 不能生成回复草稿

回复必须建立在该候选人最新、且与当前岗位 JD/rubric 一致的评估上。旧岗位配置或已经被新版本替代的 evaluation 会被拒绝，以免模型基于过期判断继续沟通。请先重新筛选或打开最新候选人结果。

### 保存评分规则时提示包含个人属性

评分规则不能把年龄、性别、婚育、民族/种族、宗教、健康/残障、政治身份等个人属性作为评分维度、硬性要求、画像条件或面试问题。`90后 / 年轻优先 / under 30` 等代理条件同样不允许。请改写为岗位相关的技能、职责、项目、任职时长、工作切换频率和可验证成果等证据。

### 增量筛选时 AI 没配置

如果全部候选人都未变化，系统可以直接跳过，不需要调用模型；只有出现需要重新评估的简历、JD 或评分规则变化时才会解析 AI 配置。

### 点击取消后为什么不是瞬间停止

如果任务正在等待一次已经发出的 BOSS/AI HTTP 请求，Python 线程不能安全地从外部中断该调用。界面会显示 `cancelling`；请求返回后任务终结，不再处理后续候选人，也不会覆盖成成功状态。

---

## ⚠️ 已知边界

- 当前主要面向本地单用户，不是中心化多租户 ATS；
- 暂无 RBAC / SSO；
- 扫描图片 PDF 暂无 OCR；
- Docker 内直接完成 BOSS 浏览器登录不如 Windows 原生环境顺畅；
- BOSS 页面、私有端点和风控策略可能变化，不承诺长期稳定；
- 运行中任务采用协作取消，不能强杀正在执行的第三方 HTTP 请求；
- 不自动发送候选人消息；
- 不自动录用或淘汰；
- 本地保存候选人数据时，使用者仍需负责组织内部访问权限、数据保留期限和合法使用。

---

## 📚 相关文档

- [快速开始](docs/getting-started.md)
- [招聘 AI CLI](docs/recruiter-ai.md)
- [招聘 Web 控制台](docs/recruiter-web.md)
- [招聘联系人数据处理](docs/recruiter-contact-handling.md)
- [招聘数据生命周期](docs/recruiter-data-lifecycle.md)
- [平台风险边界](docs/platform-risk.md)
- [排障](docs/troubleshooting.md)
- [Capability Matrix](docs/capability-matrix.md)

---

## 🤝 上游与许可证

上游项目：[`can4hou6joeng4/boss-agent-cli`](https://github.com/can4hou6joeng4/boss-agent-cli)

当前 fork：[`zerlinpi/boss-agent-cli`](https://github.com/zerlinpi/boss-agent-cli)

- Issues: <https://github.com/zerlinpi/boss-agent-cli/issues>
- Pull Requests: <https://github.com/zerlinpi/boss-agent-cli/pulls>
- Actions: <https://github.com/zerlinpi/boss-agent-cli/actions>

许可证：[MIT](LICENSE)。原作者和上游贡献者的版权与贡献历史继续保留。
