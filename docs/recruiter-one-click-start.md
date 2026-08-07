# Recruit AI 一键启动

## Windows：推荐方式

下载或更新仓库后，直接双击：

```text
start-recruiter-web.bat
```

首次启动会自动：

1. 检测 Python 3.10+；未安装时优先通过 `winget` 安装 Python 3.12。
2. 创建仓库自己的 `.venv`，不污染系统 Python。
3. 安装项目及 PDF 文本解析依赖 `pypdf`。
4. 后续仅在 `pyproject.toml` / `uv.lock` 变化时重新安装依赖。
5. 启动招聘 Web 工作台并自动打开浏览器。

默认地址：`http://127.0.0.1:8765/`。

关闭启动窗口即可停止本机服务。招聘数据仍保存在默认的 `~/.boss-agent` 数据目录。

## Docker Desktop：一键方式

Windows 双击：

```text
start-recruiter-docker.bat
```

脚本会检查并启动 Docker Desktop，然后执行专用 Compose 配置、等待健康检查通过并打开浏览器。未安装 Docker Desktop 时，在支持 `winget` 的 Windows 上会尝试安装。

手动等价命令：

```bash
docker compose -f docker-compose.recruiter.yml up -d --build
```

打开：`http://127.0.0.1:8765/`。

停止：

```text
stop-recruiter-docker.bat
```

或：

```bash
docker compose -f docker-compose.recruiter.yml down
```

招聘数据保存在名为 `boss-recruiter-data` 的 Docker volume 中，容器重建不会删除数据。需要彻底删除数据时才执行：

```bash
docker compose -f docker-compose.recruiter.yml down -v
```

## Docker 与 BOSS 浏览器能力

Docker 版适合本地简历上传、AI 评分、候选人管理和回复草稿等工作流。BOSS 登录/浏览器读取依赖真实浏览器环境，因此 Windows 本机一键启动是完整 BOSS 工作流的推荐方式。

需要让容器连接宿主机已开启 CDP 的 Chrome 时，可以设置：

```text
BOSS_CDP_URL=http://host.docker.internal:9222
```

Compose 已预置 `host.docker.internal` 映射。不要把容器端口直接发布到 `0.0.0.0`；默认 Compose 只映射到宿主机 `127.0.0.1`。
