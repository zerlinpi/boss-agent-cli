# 招聘者 AI 工作台

`boss hr ai` 将岗位配置、候选人简历评估、去重排序、人工阶段管理和回复草稿串成一个本地可审计流程。

它不会自动录用、自动淘汰或自动发送消息。涉及 BOSS 候选人简历和聊天数据的命令继续复用项目原有合规门禁；遇到验证码、风控或平台限制时必须停止并回到官方页面处理。

## 最终工作流

```text
岗位 JD + 评分规则
        ↓
本地简历目录 / BOSS 投递列表
        ↓
本地 HR 副本 + 模型安全副本
        ↓
模型侧去除姓名、联系方式、年龄、性别、婚育、政治/宗教/健康等个人属性
        ↓
按岗位相关维度评分并保存证据
        ↓
本地重算总分 + 硬条件门禁 + 模型输出安全过滤
        ↓
候选人去重、增量检测、当前岗位排行榜
        ↓
AI 追问 / 面试 / 澄清 / 婉拒草稿
        ↓
人工审核、标记阶段、输出 Top 候选人报告
```

## 1. 配置 AI

复用项目已有的 OpenAI-compatible 配置：

```bash
boss ai config \
  --provider deepseek \
  --model deepseek-chat \
  --api-key "$DEEPSEEK_API_KEY"
```

也可以使用 OpenAI、Qwen、GLM、Ollama、vLLM 或自定义兼容接口。

批量评分会复用进程内 `httpx.Client` 连接池。明确的瞬时错误（429、部分 5xx、连接失败/连接超时）会有限重试；读取超时不会自动重放，以降低重复模型调用和重复计费风险。

## 2. 保存岗位和评分规则

最小配置只需要 JD：

```bash
boss --json hr ai configure \
  --job-key java-backend \
  --jd @examples/java-backend-jd.txt \
  --boss-job-id <BOSS_JOB_ID>
```

自定义规则示例：

```json
{
  "version": "2026-08-06",
  "hard_requirements": [
    {"requirement": "Java 3 年以上", "required": true},
    {"requirement": "Spring Boot 生产经验", "required": true}
  ],
  "dimensions": [
    {"name": "required_skills", "max_score": 35, "description": "必需技术栈"},
    {"name": "relevant_experience", "max_score": 25, "description": "相关工作经验"},
    {"name": "项目复杂度", "max_score": 20, "description": "项目规模和个人贡献"},
    {"name": "achievement_evidence", "max_score": 20, "description": "量化成果"}
  ],
  "thresholds": {
    "strong_interview": 85,
    "interview": 70,
    "manual_review": 50
  },
  "max_questions": 4,
  "instructions": "优先关注订单、支付和高并发项目证据"
}
```

```bash
boss --json hr ai configure \
  --job-key java-backend \
  --jd @examples/java-backend-jd.txt \
  --rubric @java-rubric.json
```

评分规则只能使用岗位相关能力、职责、经历和成果证据。下列内容不能作为评分维度、硬条件、画像条件或建议面试问题：

- 年龄、出生日期；
- 性别、照片、外貌、身高体重；
- 婚姻、婚育、怀孕、生育计划、家庭情况；
- 民族、种族、国籍；
- 宗教、政治身份/党派；
- 健康、疾病、残障；
- `90后 / 年轻优先 / under 30 / born after 1995` 等年龄代理条件；
- 其他与岗位能力无关的个人属性。

该限制由本地 `normalize_rubric()` 强制执行，不只依赖模型提示词。AI 岗位分析返回的标题、候选人画像和建议面试问题也使用同一门禁。直接调用 `RecruiterAIStore.save_job()` 或 `save_evaluation()` 也不能绕过该契约。

评分维度会做 Unicode-safe 的 canonicalization，因此 `required_skills / RequiredSkills / Required Skills / required-skills` 可以匹配同一维度，同时 `后端经验 / 项目复杂度` 等中文自定义维度也可以正常使用。归一化后重复的维度或硬性要求会被拒绝。

查看岗位配置：

```bash
boss --json hr ai jobs
```

## 3. 批量筛选本地简历

输入目录中的文件应为结构化 JSON。可以直接保存 `boss hr resume --json` 的输出，也可以使用本系统约定的 `basic/work_experience/project_experience/education` 结构。

```bash
boss --json hr ai screen \
  --job-key java-backend \
  --resume-dir ./candidate-resumes \
  --pattern "*.json" \
  --limit 100 \
  --top 20
```

再次执行时，系统会根据以下输入判断是否真的发生变化：

- 稳定候选人标识；
- 简历指纹；
- **岗位 JD**；
- 评分规则指纹。

只修改 JD、即使 rubric 完全不变，也会触发重新评估。需要无条件重评时添加：

```bash
--force
```

本地文件使用规范化来源路径形成稳定候选人身份。因此同一路径的简历内容更新会形成同一候选人的新评估版本，而不是新的人才记录。

如果本轮所有候选人都未变化，CLI 不需要提前加载 AI 配置；即使当前没有配置 AI，也能完成增量检查。只有实际需要重新评分或生成新草稿时才解析 AI 服务配置。

CLI 批量筛选会在当前 `RecruiterAIStore` 生命周期内复用 latest-candidate 索引，避免每份简历重新扫描整个 `evaluations/` 目录；本轮保存新评估或目录发生外部变化时缓存会更新/失效。

为本轮新评估候选人中的前 5 名生成回复草稿：

```bash
boss --json hr ai screen \
  --job-key java-backend \
  --resume-dir ./candidate-resumes \
  --draft-top 5
```

`draft-top` 不会重新给历史未变化的 Top 候选人生成草稿。增量重跑全部 `skipped` 时，不会因为 `draft-top` 再触发模型调用。

## 4. 筛选 BOSS 投递列表

该命令会按页读取指定职位的投递列表、获取可用的在线简历、逐人评估并生成排行榜。默认不会读取聊天，也不会发送消息。

```bash
boss config set operating_mode research
boss login

boss --json hr ai screen-applications \
  --job-key java-backend \
  --job-id <BOSS_JOB_ID> \
  --pages 2 \
  --limit 30 \
  --top 15
```

BOSS 候选人的稳定身份优先使用 `geek_id`，再退到其他平台 ID。分页读取会对同一候选人去重，避免分页边界重复拉取简历；`--force` 也不会因为分页重复而对同一候选人重复评分。

为本轮实际新评估的前 5 名生成回复草稿，并在可用时读取聊天上下文：

```bash
boss --json hr ai screen-applications \
  --job-key java-backend \
  --job-id <BOSS_JOB_ID> \
  --limit 30 \
  --draft-top 5 \
  --include-chat
```

历史未变化候选人不会因为仍位于历史排行榜前列就重复读取聊天或重新生成自动草稿。

输出中的 `messages_sent` 始终为 `0`。招聘人员必须审核草稿后回到 BOSS 官方页面发送。

候选人列表缺少必要的平台标识时，该候选人会进入 `failed`，不会影响其他候选人继续处理。

## 5. 评估单个候选人

本地 JSON：

```bash
boss --json hr ai evaluate \
  --job-key java-backend \
  --resume @candidate.json
```

`@candidate.json` 同样会把文件路径作为稳定候选人身份。重复执行时只有在**简历、JD 和评分规则都未变化**时，才会直接返回原评估记录而不调用模型。

直接读取 BOSS 候选人：

```bash
boss --json hr ai evaluate-geek <GEEK_ID> \
  --job-id <BOSS_JOB_ID> \
  --security-id <SECURITY_ID> \
  --friend-id <FRIEND_ID> \
  --job-key java-backend
```

## 6. 查看排行榜和最终报告

```bash
boss --json hr ai rank --job-key java-backend --top 20
```

```bash
boss --json hr ai report --job-key java-backend --top 10
```

对于**已保存的岗位**，当前排名和报告只统计与当前保存的 JD + rubric 一致的评估。修改岗位后，历史 JSON 不会删除，但旧评估会进入 stale 状态，直到候选人重新评估。

`report` 返回：

- 当前配置下去重后的候选人数；
- `stale_count`：最新候选人版本中基于旧 JD/rubric、等待重评的数量；
- `strong_interview / interview / manual_review / not_recommended` 分组；
- 招聘人员手工阶段统计；
- Top 候选人分数、证据、风险、待追问问题和来源；
- `human_review_required: true`。

没有保存岗位配置的 ad-hoc CLI 评估仍可按 `job_key` 排名，不会因为缺少岗位文件而被全部视为 stale。岗位文件如果存在但损坏，则会直接返回结构化错误，不会退回历史结果。

候选人的历史 `created_at` 即使混用 `Z`、`+08:00` 或无时区格式，也会先转换为实际 UTC 时间再选择最新版本和处理并列排序。

Web 候选人列表的排名、报告和分析在同一次请求中共享 latest-candidate 索引；CLI `report` 也复用同一次历史加载，不会为了 Top candidates 再扫描一次目录。

## 7. 生成 AI 回复草稿

自动根据评分结果选择追问、面试邀请、澄清或婉拒草稿：

```bash
boss --json hr ai reply \
  --evaluation-id <EVALUATION_ID> \
  --intent auto
```

结合聊天上下文：

```bash
boss --json hr ai reply \
  --evaluation-id <EVALUATION_ID> \
  --conversation @chat.txt \
  --intent auto
```

也可以显式指定：

- `acknowledge`
- `ask_followup`
- `invite_interview`
- `clarify`
- `decline_draft`

回复必须关联真实 evaluation，不允许生成孤儿 reply 记录，而且该 evaluation 必须：

1. 是同一逻辑候选人的最新版本；
2. 对于已保存岗位，仍与当前 JD 和 rubric 一致。

旧 JD、旧评分规则或已经被新评估替代的 evaluation 会被拒绝。Web 返回 `STALE_EVALUATION` / HTTP 409；CLI 会在加载 AI 配置和调用模型之前返回结构化输入错误。因此旧历史记录仍可审计，但不能直接成为新的 AI 沟通依据。

所有草稿都包含 `requires_human_review: true`。本地规则会额外扫描：

- 受保护属性询问；
- 确定录用/Offer 承诺，例如“我们决定录用你 / 欢迎入职”；
- 电话、邮箱、微信、QQ 等联系方式异常暴露；
- 身份证、护照、住宅地址等高风险身份数据暴露；
- 异常长回复。

草稿保存在：

```text
~/.boss-agent/recruiter-ai/replies/
```

## 8. 人工管理候选人阶段

```bash
boss --json hr ai mark \
  --evaluation-id <EVALUATION_ID> \
  --status shortlisted \
  --note "建议安排技术初面"
```

可用状态：

- `new`
- `shortlisted`
- `interview`
- `hold`
- `rejected`
- `hired`

人工阶段和备注属于逻辑候选人，而不是某一个 AI 评估版本。对旧 evaluation ID 执行 `mark` 时，同一候选人的所有历史版本都会同步状态；后续新评估版本也会继承最新人工状态和备注。

该操作只更新本地记录，不修改 BOSS 平台状态。

## 评分可靠性

模型提供各维度分数和证据，但最终 `total_score` 由本地代码根据维度分数重新计算，模型无法直接决定总分。

评分维度名称会进行 Unicode-safe 的大小写、camelCase、空格和标点归一。例如配置 `required_skills` 时，模型返回 `RequiredSkills / Required Skills / required-skills` 不会导致该维度意外归零；中文维度名不会因为归一化被丢失。

模型自行增加的未知维度不会进入本地总分；自行增加的未配置硬条件也不会进入正式硬条件结果。

硬性要求同样做大小写和多余空白归一；配置 `Java`、模型返回 `  java  ` 时会匹配同一标准条件，并保留配置中的 `Java` 作为输出名称。

模型输出不是直接写入 UI：维度 evidence/reason、硬条件 evidence、strengths、concerns、next questions 和 summary 还会经过本地安全过滤。如果模型自行输出年龄、婚育、性别、政治/宗教/健康信息或联系方式，该内容会被移除；违规 evidence 不能继续支撑正分，同时结果强制降级为 `manual_review` 并记录安全标记。

如果必需硬条件被标记为 `missing` 或 `unclear`，推荐结果会强制变为 `manual_review`，防止信息缺失时自动形成不利决定。

## 本地数据与高风险身份数据

本地人工流程可以保留：

- 姓名；
- 手机/座机；
- 邮箱；
- 微信；
- QQ；
- 招聘阶段和人工备注；
- 用于沟通的聊天内容。

但身份证、护照、住宅详细地址不属于日常约面所需数据。标准化简历、直接 `Store.save_evaluation()`、增量指纹查询和 reply conversation 使用同一清理策略：

- 连续或常见空格/短横线格式的身份证号会移除；
- `passport / passportNo / 护照号` 等结构化字段会移除；
- 带明确标签的护照号码会移除；
- 家庭住址、现住址、居住地址、住宅地址等会移除；
- `面试地址` 等招聘流程信息不会被住宅地址规则误删。

模型输入还会进一步去除姓名、联系方式和受保护属性，因此“本地 HR 可见信息”和“AI 决策输入”仍是两条独立通道。

## 数据目录

```text
~/.boss-agent/recruiter-ai/
├── jobs/
├── evaluations/
└── replies/
```

这些文件仍可能包含候选人姓名、联系方式和聊天上下文，应限制目录权限、设置保留期限，并在招聘流程结束后按公司的个人信息管理制度清理。