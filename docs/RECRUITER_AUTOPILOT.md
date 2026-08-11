# Recruiter Autopilot

Recruiter Autopilot is the unattended **collection and analysis** layer of BOSS Recruit AI.
It synchronizes current BOSS recruiter jobs and applications, parses candidate resumes,
runs the existing evidence-based AI evaluation, updates local rankings, and creates reply
drafts for human review.

It intentionally does **not** automatically reject, hire, invite, or send messages to candidates.
Final employment decisions and external communications remain human actions.

## What one run does

```text
BOSS current jobs
  -> match existing local job configs
  -> optionally fetch JD and auto-create missing local job configs
  -> page through applications for every selected job
  -> de-duplicate candidate references
  -> freshness check against the current JD/rubric version
  -> fetch candidate resume/profile when needed
  -> existing protected-attribute redaction / evidence-based AI evaluation
  -> persist evaluation
  -> rank current candidates
  -> create reply drafts for newly evaluated top candidates
  -> local Web/Kanban/review workflow
```

The sync ledger is stored at:

```text
~/.boss-agent/recruiter-ai/autopilot-state.json
```

The ledger is only an optimization cache. Authoritative evaluations remain in the existing
`recruiter-ai/evaluations` directory. A corrupt ledger is quarantined and rebuilt.

## Prerequisites

Install and initialize the project first on Windows:

```powershell
git clone https://github.com/zerlinpi/boss-agent-cli.git
cd boss-agent-cli
.\start-recruiter-web.bat
```

Configure AI, log in to BOSS, then enable Research Mode explicitly:

```powershell
.\.venv\Scripts\boss.exe ai config
.\.venv\Scripts\boss.exe status
.\.venv\Scripts\boss.exe config set operating_mode research
```

Research Mode is required because Autopilot reads authorized recruiter application and resume data.
Do not use it for accounts/data you are not authorized to access. If BOSS shows a CAPTCHA,
verification prompt, risk-control warning, or permission failure, resolve that in the official/user-visible
session instead of attempting to bypass it.

## First live validation

Before a full run, test one configured job with a low cap:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot `
  --job-key <JOB_KEY> `
  --max-pages 1 `
  --max-candidates-per-job 5 `
  --draft-top 2 `
  --refresh-seen-hours 0
```

Verify:

1. The expected BOSS job is selected.
2. Expected candidates are discovered.
3. `view_geek` succeeds for the test candidates.
4. Evaluations appear in the Web candidate list.
5. Scores contain evidence and protected traits are not used.
6. Reply drafts are generated locally.
7. Output still reports `messages_sent: 0` and `human_review_required: true`.

## Normal all-job run

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot
```

Recommended explicit production command:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot `
  --max-pages 30 `
  --max-candidates-per-job 2000 `
  --refresh-seen-hours 24 `
  --top 50 `
  --draft-top 10 `
  --auto-configure
```

If reply drafting should include recent chat context:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot --include-chat
```

Force a full re-fetch/re-evaluation only when deliberately required:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot --force
```

For accounts with more historical applications, raise the explicit caps as needed:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot `
  --max-pages 100 `
  --max-candidates-per-job 10000
```

The caps are intentional safety limits. A successful run reports the number of pages and candidates
actually discovered per job, so coverage can be reviewed instead of silently assuming infinity.

## Incremental behavior

By default an already-processed candidate is not re-fetched for 24 hours when all of the following remain true:

- the sync ledger entry is recent;
- its referenced evaluation still exists;
- the evaluation belongs to the same local job;
- the saved JD is unchanged;
- the rubric fingerprint is unchanged.

After the freshness window expires, the candidate profile is re-fetched. The existing resume/rubric fingerprint
check still prevents a new AI evaluation when the resume and scoring contract are unchanged.

Use another interval if desired:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot --refresh-seen-hours 6
```

Always check every run, while still retaining resume fingerprint de-duplication:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot --refresh-seen-hours 0
```

## Auto-configuring current BOSS jobs

Default behavior is `--auto-configure`.
For a current BOSS job that has no local `boss_job_id` mapping, Autopilot attempts to:

1. read the BOSS job detail;
2. extract an explicit JD field;
3. create a local job key derived from the BOSS job ID;
4. store the BOSS job ID/title in metadata;
5. use the standard protected-attribute-safe default rubric.

If job-detail parsing cannot identify a JD safely, that job is reported under
`unconfigured_platform_jobs` instead of guessing from arbitrary page text.

Disable auto-configuration when every job must be manually reviewed first:

```powershell
.\.venv\Scripts\boss.exe hr ai autopilot --no-auto-configure
```

## Web usage

Start the Web console:

```powershell
.\start-recruiter-web.bat
```

Open:

```text
http://127.0.0.1:8765/
```

In **智能筛选**, the `Recruiter Autopilot · 全职位增量同步` panel exposes:

- maximum pages per job;
- candidate cap per job;
- freshness interval;
- reply draft count;
- auto-configure jobs;
- optional chat context;
- force refresh.

The operation runs through the existing persistent background task registry. It is visible in
**任务与审计**, can use the existing cancellation controls, and cannot overlap another Web screening task.
A cross-process OS lock also prevents the Web UI, manual CLI, and Windows scheduler from running the same
Autopilot simultaneously.

## Windows daily scheduling

Initialize the project first, complete BOSS login and AI configuration, and set Research Mode:

```powershell
.\.venv\Scripts\boss.exe config set operating_mode research
```

Install the default daily 09:00 task:

```powershell
.\install-recruiter-autopilot-task.bat
```

Or choose a time and limits:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\install-recruiter-autopilot-task.ps1 `
  -DailyAt "09:00" `
  -MaxPages 30 `
  -MaxCandidatesPerJob 2000 `
  -RefreshSeenHours 24 `
  -DraftTop 10
```

The scheduled task intentionally uses the current user's **interactive logon session**. This is important for
a BOSS/CDP/browser-backed login. It does not try to hide an interactive authentication requirement in a
non-interactive Windows service session.

Run it immediately:

```powershell
Start-ScheduledTask -TaskName "BOSS Recruit AI Autopilot"
```

Inspect status:

```powershell
Get-ScheduledTask -TaskName "BOSS Recruit AI Autopilot" | Get-ScheduledTaskInfo
```

Logs:

```text
~/.boss-agent/logs/recruiter-autopilot.log
```

Remove the schedule:

```powershell
Unregister-ScheduledTask -TaskName "BOSS Recruit AI Autopilot" -Confirm:$false
```

## Operational guardrails

- Autopilot does not bypass CAPTCHA, verification, account risk controls, or platform permissions.
- It does not send reply drafts automatically.
- It does not automatically mark candidates `rejected` or `hired`.
- AI rankings are decision support, not final employment decisions.
- Job scoring rules continue to reject protected-trait criteria such as age, gender, marital/family status,
  ethnicity/race, religion, disability/health, political affiliation and similar personal attributes.
- Candidate status changes and final communication remain auditable human actions.
