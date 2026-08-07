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
本地重算总分 + 硬条件门禁
        ↓
候选人去重、增量检测、排行榜
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
    {"name": "project_evidence", "max_score": 20, "description": "项目规模和个人贡献"},
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

评分规则只能使用岗位相关能力、职责、经历和成果证据。下列内容不能作为评分维度、硬条件或指令：

- 年龄、出生日期；
- 性别、照片、外貌、身高体重；
- 婚姻、婚育、怀孕、生育计划、家庭情况；
- 民族、种族、国籍；
- 宗教、政治身份/党派；
- 健康、疾病、残障；
- 其他与岗位能力无关的个人属性。

该限制由本地 `normalize_rubric()` 强制执行，不只依赖模型提示词。AI 岗位分析返回的标题、候选人画像和建议面试问题也使用同一门禁。

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

再次执行时，系统会根据候选人标识、简历指纹和评分规则指纹跳过未发生变化的记录。需要强制重评时添加：

```bash
--force
```

本地文件使用规范化来源路径形成稳定候选人身份。因此同一路径的简历内容更新会形成同一候选人的新评估版本，而不是新的人才记录。

如果本轮所有候选人都未变化，CLI 不需要提前加载 AI 配置；即使当前没有配置 AI，也能完成增量检查。只有实际需要重新评分或生成新草稿时才解析 AI 服务配置。

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

BOSS 候选人的稳定身份优先使用 `geek_id`，避免聊天会话 `friend_id` 变化时把同一候选人误判成新人。

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

候选人列表缺少 `geek_id` 或 `security_id` 时，该候选人会进入 `failed`，不会影响其他候选人继续处理。

## 5. 评估单个候选人

本地 JSON：

```bash
boss --json hr ai evaluate \
  --job-key java-backend \
  --resume @candidate.json
```

`@candidate.json` 同样会把文件路径作为稳定候选人身份。重复执行时若简历和评分规则均未变化，可以直接返回原评估记录而不调用模型。

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

`report` 返回：

- 去重后的候选人数；
- `strong_interview / interview / manual_review / not_recommended` 分组；
- 招聘人员手工阶段统计；
- Top 候选人分数、证据、风险、待追问问题和来源；
- `human_review_required: true`。

Web 候选人列表的排名、报告和分析在同一次请求中共享 latest-candidate 索引，避免多次重复扫描评估目录。

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

所有草稿都包含 `requires_human_review: true`。本地规则会额外扫描：

- 受保护属性询问；
- 确定录用/Offer 承诺；
- 电话、邮箱、微信、QQ 等联系方式异常暴露；
- 异常长回复。

草稿保存在：

```text
~/.boss-agent/recruiter-ai/replies/
```

回复必须关联真实 evaluation，不允许生成孤儿 reply 记录。

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

评分维度名称会进行大小写、空格和连字符归一，例如配置 `required_skills` 时，模型返回 `Required Skills` 不会导致该维度意外归零。模型自行增加的未知维度不会进入本地总分。

硬性要求同样做大小写和多余空白归一；配置 `Java`、模型返回 `  java  ` 时会匹配同一标准条件，并保留配置中的 `Java` 作为输出名称。

如果必需硬条件被标记为 `missing` 或 `unclear`，推荐结果会强制变为 `manual_review`，防止信息缺失时自动形成不利决定。

系统会保存：

- JD；
- 评分规则及版本；
- 简历指纹；
- 候选人来源；
- 各维度评分和证据；
- AI 置信度；
- 人工阶段和备注；
- 回复草稿。

## 数据目录

```text
~/.boss-agent/recruiter-ai/
├── jobs/
├── evaluations/
└── replies/
```

这些文件可能包含候选人简历和聊天上下文，应限制目录权限、设置保留期限，并在招聘流程结束后按公司的个人信息管理制度清理。
