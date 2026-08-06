# 招聘者 AI 工作台

`boss hr ai` 将岗位配置、候选人简历评估、去重排序、人工阶段管理和回复草稿串成一个本地可审计流程。

它不会自动录用、自动淘汰或自动发送消息。涉及 BOSS 候选人简历和聊天数据的命令继续复用项目原有合规门禁；遇到验证码、风控或平台限制时必须停止并回到官方页面处理。

## 最终工作流

```text
岗位 JD + 评分规则
        ↓
本地简历目录 / BOSS 投递列表
        ↓
去除年龄、性别、照片、婚育、联系方式等字段
        ↓
按维度评分并保存证据
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

为前 5 名同时生成回复草稿：

```bash
boss --json hr ai screen \
  --job-key java-backend \
  --resume-dir ./candidate-resumes \
  --draft-top 5
```

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

为前 5 名生成回复草稿，并在可用时读取聊天上下文：

```bash
boss --json hr ai screen-applications \
  --job-key java-backend \
  --job-id <BOSS_JOB_ID> \
  --limit 30 \
  --draft-top 5 \
  --include-chat
```

输出中的 `messages_sent` 始终为 `0`。招聘人员必须审核草稿后回到 BOSS 官方页面发送。

候选人列表缺少 `geek_id` 或 `security_id` 时，该候选人会进入 `failed`，不会影响其他候选人继续处理。

## 5. 评估单个候选人

本地 JSON：

```bash
boss --json hr ai evaluate \
  --job-key java-backend \
  --resume @candidate.json
```

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

所有草稿都包含 `requires_human_review: true`，并保存在：

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

该操作只更新本地记录，不修改 BOSS 平台状态。

## 评分可靠性

模型提供各维度分数和证据，但最终 `total_score` 由本地代码根据维度分数重新计算，模型无法直接决定总分。

如果必需硬条件被标记为 `missing` 或 `unclear`，推荐结果会强制变为 `manual_review`，防止信息缺失时自动淘汰候选人。

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
