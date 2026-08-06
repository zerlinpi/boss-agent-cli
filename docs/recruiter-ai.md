# 招聘者 AI 工作台

`boss hr ai` 在现有招聘者命令之上增加本地、可审计的 AI 简历筛选能力。它不会自动发送消息，也不会绕过仓库原有的合规门禁。

## 能力

- 对单份结构化简历按 JD 生成 0–100 分的证据化评估
- 在 Research Mode 的合规门禁下读取并评估指定 BOSS 候选人
- 批量评估 JSON 简历目录并输出候选人排行榜
- 根据评估结果和聊天上下文生成待人工审核的回复草稿
- 本地保存评估、评分版本输入、候选人来源和回复草稿
- 评估前自动移除姓名、联系方式、性别、年龄、头像等不参与评分的数据

## 配置 AI

复用项目已有的 OpenAI-compatible AI 配置：

```bash
boss ai config \
  --provider deepseek \
  --model deepseek-chat \
  --api-key "$DEEPSEEK_API_KEY"
```

也可以使用 Ollama、vLLM 或其他兼容接口。

## 评估单份本地简历

简历文件可以是 `boss hr resume --json` 的完整输出信封，也可以直接是结构化简历对象。

```bash
boss --json hr ai evaluate \
  --jd @examples/java-backend-jd.txt \
  --resume @candidate.json \
  --job-key java-backend
```

结果会保存到：

```text
~/.boss-agent/recruiter-ai/evaluations/
```

使用 `--no-save` 可以只查看结果而不落盘。

## 直接评估 BOSS 候选人

该命令复用 `recruiter-resume` 的合规门禁。默认 Assisted Mode 会阻断，需要在已授权、受控的 Research Mode 中使用：

```bash
boss config set operating_mode research
boss login

boss --json hr ai evaluate-geek <geek_id> \
  --job-id <job_id> \
  --security-id <security_id> \
  --jd @examples/java-backend-jd.txt \
  --job-key java-backend
```

遇到验证码、账号验证、风险提示或平台限制时应立即停止，并回到官方页面人工处理。

## 批量筛选

将候选人结构化简历放到同一个目录：

```bash
boss --json hr ai batch \
  --jd @examples/java-backend-jd.txt \
  --resume-dir ./candidate-resumes \
  --pattern "*.json" \
  --job-key java-backend \
  --top 10 \
  --limit 50
```

批量命令逐份处理，单个文件失败不会中断全部任务。输出包含失败文件和当前排行榜。

## 查看排行榜

```bash
boss --json hr ai rank --job-key java-backend --top 10
```

排行榜包含：

- 匹配总分
- 推荐等级
- 置信度
- 优势
- 风险项
- 评估摘要
- 可用于后续生成回复的 `evaluation_id`

## 生成回复草稿

先把必要的聊天上下文保存成纯文本，然后执行：

```bash
boss --json hr ai reply \
  --evaluation-id <evaluation_id> \
  --conversation @chat.txt \
  --intent ask_followup
```

支持的 intent：

- `acknowledge`：确认已收到资料
- `ask_followup`：追问关键信息
- `invite_interview`：生成面试邀请草稿
- `clarify`：澄清岗位或候选人信息
- `decline_draft`：生成婉拒草稿

生成结果始终包含 `requires_human_review: true`，并保存在：

```text
~/.boss-agent/recruiter-ai/replies/
```

发送动作不在该模块内完成。招聘人员需要检查事实、薪资、时间和表达后，回到 BOSS 官方页面发送。

## 评分输出

模型必须输出以下核心字段：

```json
{
  "candidate_name": "张三",
  "total_score": 86,
  "recommendation": "interview",
  "confidence": 0.82,
  "hard_requirements": [],
  "dimensions": [],
  "strengths": [],
  "concerns": [],
  "next_questions": [],
  "summary": "建议人工复核后进入技术初面。",
  "human_review_required": true
}
```

允许的推荐等级：

- `strong_interview`
- `interview`
- `manual_review`
- `not_recommended`

推荐等级只能作为招聘人员的辅助信息，不能作为自动淘汰或自动录用的唯一依据。
