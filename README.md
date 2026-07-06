# Personal Job Application Agent

本项目是一个本地运行的求职申请助手 MVP。用户可以上传 PDF 或 DOCX 简历，并粘贴岗位 JD 文本或输入单个岗位网页 URL。系统会解析岗位信息，分析简历与岗位的匹配度，生成简历优化建议和英文 Cover Letter。

## 功能列表

- 上传 PDF 或 DOCX 简历
- 粘贴岗位 JD 文本
- 输入单个岗位网页 URL 并提取正文
- 使用 DeepSeek API 分析岗位匹配度
- 输出岗位摘要、匹配分数、匹配原因、匹配技能、缺失技能
- 生成中文简历优化建议
- 生成英文 Cover Letter

## 技术栈

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Resume parsing: pypdf, python-docx
- URL extraction: requests, beautifulsoup4
- Storage: 本地临时处理，无数据库

## 项目结构

```text
.
├── backend/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       └── styles.css
├── .env.example
├── .gitignore
└── README.md
```

## 本地运行步骤

确保项目根目录存在 `.env`，并配置 DeepSeek API Key：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

安装并启动后端，再安装并启动前端。

## 后端启动命令

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端默认地址：

```text
http://localhost:8000
```

公网开发访问地址：

```text
http://101.34.61.52:8000
```

## 前端启动命令

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

前端默认地址：

```text
http://localhost:5173
```

iPad 或其他设备访问：

```text
http://101.34.61.52:5173
```

如需配置 API 地址，可在 `frontend/.env` 中设置：

```bash
VITE_API_BASE_URL=http://101.34.61.52:8000
```

也可以参考 `frontend/.env.example`。

## 从局域网/公网访问开发服务器

前端 Vite dev server 已配置为监听 `0.0.0.0:5173`，并允许通过 `101.34.61.52` 访问。后端 FastAPI 需要监听 `0.0.0.0:8000`。

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

如果还没有虚拟环境，先执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

iPad 浏览器访问：

```text
http://101.34.61.52:5173
```

如果无法从 iPad 访问，需要检查云服务器安全组或系统防火墙是否开放 TCP 端口 `5173` 和 `8000`。不要随意修改云服务器安全组；确认规则后再调整。

如果系统启用了 `ufw`，可以按需执行：

```bash
sudo ufw allow 5173/tcp
sudo ufw allow 8000/tcp
sudo ufw status
```

安全提醒：

- 当前配置只是开发环境公网访问，不要作为正式生产部署。
- 不要暴露 `.env`，不要提交真实 API Key。
- 不要在日志或前端页面中打印 DeepSeek API Key。
- 正式部署建议使用 Nginx + HTTPS + 后端反向代理。

## .env 配置说明

项目根目录 `.env` 需要包含：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

不要把真实 API Key 写入代码，不要提交 `.env`。

## API 示例

接口：

```text
POST /api/analyze
```

请求参数使用 `multipart/form-data`：

- `resume`: 必填，PDF 或 DOCX 文件
- `job_text`: 可选，岗位描述文本
- `job_url`: 可选，单个岗位网页 URL

如果同时提供 `job_text` 和 `job_url`，系统优先使用 `job_text`。

示例：

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "resume=@/path/to/resume.pdf" \
  -F "job_text=We are hiring a full-stack engineer..."
```

返回格式：

```json
{
  "job_summary": "string",
  "match_score": 0,
  "match_reason": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "resume_suggestions": ["string"],
  "cover_letter": "string"
}
```

## 注意事项

- 上传文件仅用于当前分析，不保存到长期数据库。
- 不自动批量爬取 JobsDB 或任何求职网站。
- 只处理用户提供的单个 URL 或用户粘贴的 JD 文本。
- 不要提交真实 API Key。
- `.env` 已加入 `.gitignore`。
- 本项目只初始化本地 git 仓库，不创建 GitHub 仓库，不执行 `git push`。

## Roadmap

- 增加用户登录
- 增加历史分析记录
- 增加岗位收藏
- 增加多语言 Cover Letter
- 增加更准确的评分规则
- 增加简历关键词优化
- 增加导出 PDF/DOCX 功能
