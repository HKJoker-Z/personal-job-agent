# Behavior-Preserving Simplification Phase 1 Work Report

## Delivery metadata

- 日期：2026-08-14
- 仓库：https://github.com/HKJoker-Z/personal-job-agent
- 分支：`refactor/behavior-preserving-simplification-phase-1`
- 基线 SHA：`0e71307b61757d2ef47cd55b08beb62ada96bf57`
- 最终实现 SHA：`91be64aeff50229d1cd4e60a451df6d42e7168a0`
- 基线版本：`v2.0.6`（`git describe`：`v2.0.6-6-g0e71307`）
- Alembic 基线及重构后：`20260730_07 (head)`；`current` 与 `heads` 均一致

本报告及索引是交付文档提交的一部分；最终实现 SHA 指包含代码改动的提交，后续文档提交不改变运行时代码。

## 问题与本阶段范围

重构前 `backend/main.py` 通过 `from legacy_application import *` 暴露大量隐式符号，并直接调用 `extend_application`。应用组合逻辑虽然已经存在于 `backend/app/application.py`，但公开入口和兼容入口的职责不够清晰，增加了读取、测试和后续迁移路由时的误解风险。

本阶段选择一个可以独立审查和回滚的切片：统一 ASGI 入口到 `create_application()`，保留兼容测试/调用入口，并显式保留当前已被外部导入的三个模块级符号。由于 `legacy_application.py`、前端单文件和领域路由的整体拆分会同时改变大量导入、挂载顺序和测试夹具，本阶段没有强行合并这些高风险改动。

## 修改、移动、删除与保留

修改：

- `backend/main.py` 删除通配符导入，改为调用唯一的 `create_application()`。
- `backend/main.py` 显式保留 `health_check`、`project_knowledge_status_data` 和 `write_project_knowledge_file` 三个已发现的兼容导出。
- `backend/app/application.py` 将实际拼装体收为 `_compose_application()`；`create_application()` 构造生产 ASGI 应用，`extend_application()` 保留为兼容适配入口。
- 保持现有 router 注册顺序、中间件注册顺序、legacy FastAPI app 对象和设置读取方式不变。

移动：无。

删除：无运行时领域实现、路由、测试、数据库对象或兼容代码被删除。

明确保留：`legacy_application.py` 中的 Analyze、Provider、History、Project Knowledge、Monitoring、Resume 解析和兼容路径；Java normalization、Redis、Worker、Outbox、历史 Agent Run、Compose 文件、生产环境变量、前端 `legacy-workspace.jsx` 及其样式。

## 行为保持依据

`_compose_application()` 的注册体和调用顺序未改变；生产入口现在仍以相同的 `legacy_application.app` 为基础，只是通过 `create_application()` 进入。`extend_application()` 仍返回同一个被组合的 app，供现有测试夹具和兼容调用方使用。显式导出是根据仓库引用搜索和完整测试中实际失败的兼容导入补回的，而不是继续暴露未知符号。

重构前后递归展开的 FastAPI 路由清单均为 50 个 method/path 项；中间件顺序均为：
`RequestLoggingMiddleware` → `V2SecurityMiddleware` → `FeatureRetirementMiddleware` → `AnalyzeIdempotencyFailureMiddleware` → `CORSMiddleware`。

本切片没有修改 API handler、Pydantic schema、数据库访问、配置默认值、前端交互或部署文件，因此没有对用户可见 API、结果语义、数据库 Schema 或生产拓扑作有意改变。验证证据支持“本切片的入口组合行为保持”，不将其扩大表述为整个仓库的零回归保证。

## 规模与复杂度对比

| 范围 | 基线行数 | 重构后行数 | 说明 |
|---|---:|---:|---|
| `backend/main.py` | 9 | 13 | 删除 wildcard；增加工厂入口和兼容导出的显式说明 |
| `backend/app/application.py` | 50 | 56 | 组合体改为私有实现；保留带文档的兼容适配器 |
| `backend/legacy_application.py` | 4,445 | 4,445 | 未触碰 |
| `frontend/src/legacy-workspace.jsx` | 2,732 | 2,732 | 未触碰 |

两个入口文件合计净增加 10 行，行数不是本切片的优化指标；主要收益是去掉隐式 wildcard API、明确唯一 ASGI factory，并把兼容入口与实际组合实现分开。Analyze/Provider/History/Project Knowledge/Monitoring 和前端拆分保留到后续可独立验证的切片。

## 执行过的命令及真实结果

### 基线

- `git fetch origin main`、工作树检查、分支创建：通过；基线为 `0e71307b61757d2ef47cd55b08beb62ada96bf57`，工作树干净。
- `APP_ENV=development PYTHONPATH=backend backend/.venv/bin/alembic -c backend/alembic.ini current` 与 `heads`：均为 `20260730_07 (head)`。
- `APP_ENV=test APP_DATABASE_PATH=/tmp/pja-baseline.db PYTHONPATH=. .venv/bin/python -m unittest discover -v`：首次因继承的 SOCKS proxy 环境而失败（本地环境缺少 `socksio`，不是代码断言变化）。
- 取消 `ALL_PROXY/HTTP_PROXY/HTTPS_PROXY` 等代理变量后重新执行同一后端全套：`Ran 555 tests in 252.148s`，`OK (skipped=12)`；跳过项为显式 opt-in 的 PostgreSQL 集成测试。
- `npm run test`：9 个测试文件、70 个测试通过。
- `npm run build`：Vite production build 通过。
- `python3 -m compileall -q backend scripts`：通过。
- 首次 `docker compose --env-file .env.production -f compose.yaml -f compose.test.yaml config --quiet`：因本地 `.env.production` 缺少必填变量失败；使用仅含测试占位值的内联环境变量重新验证，同一 Compose 配置通过。未读取或写入任何真实凭据。
- 基线递归路由清单：50 个 method/path 项；基线中间件顺序记录如上。

### 重构后

- `git diff --check`：通过。
- `PYTHONPATH=. APP_ENV=test ... .venv/bin/python -m unittest ...`（中间件组合、生产 API docs 路由、trusted host、CORS）：4 个测试通过。
- `PYTHONPATH=. APP_ENV=test ... .venv/bin/python -m unittest ...`（`health_check`、Project Knowledge 配置兼容导入）：2 个测试通过。该检查曾在去掉 wildcard 后发现 2 个导入错误，补回三个显式兼容导出后通过。
- 取消代理变量后后端全套：`Ran 555 tests in 265.418s`，`OK (skipped=12)`；无新增 upgrade 操作。
- `npm run test && npm run build`：9 个测试文件、70 个测试通过；Vite production build 通过。
- `python3 -m compileall -q backend scripts`：通过。
- Alembic `current` 与 `heads`：仍均为 `20260730_07 (head)`。
- `docker compose -f compose.yaml -f compose.test.yaml config --quiet`：通过。
- `docker compose -f deploy/production/compose.yaml config --quiet`：使用测试占位值通过。
- `scripts/test-v201-production-runtime.sh`：`Version 2.0.2 production runtime regression tests passed.`
- 隔离 PostgreSQL 16.9 容器上的 `test_v2_postgres_integration.py`：`Ran 12 tests in 46.791s`，`OK`；临时容器已清理。
- `docker build --file backend/Dockerfile ...`、`docker build --file frontend/Dockerfile ...` 及 `scripts/verify-images.sh`：两个镜像构建通过，用户和敏感路径检查通过；只创建本地临时镜像 tag。
- `PJA_SMOKE_MILESTONE=2.0.6 PJA_APP_VERSION=2.0.6 PJA_TEST_PROJECT=pja-v2-final-refactor-20260814 PJA_TEST_HTTP_PORT=18098 PJA_TEST_POSTGRES_PORT=15448 scripts/docker-smoke-v2.sh`：通过。覆盖 fresh Alembic upgrade/current=head、管理员初始化、登录/Remember Me/Session/CSRF、Project Knowledge/RAG、Analyze（知识库关闭和开启）、DOCX Resume、重启后的数据库和私有文件持久化、备份 manifest/checksum 及恢复验证。
- 独立临时数据库 API 合约检查：History 详情、状态/备注更新、next-action、PDF/DOCX 导出（`Content-Type` 与 attachment header）、删除及删除后 404：通过。输入均为合成记录。

关键 Analyze 场景由完整测试、V2.0.6 smoke 和对应测试模块共同覆盖：complete/partial/fallback、输入安全阻断、RAG on/off、Stored Resume 与临时 PDF/DOCX、History on/off、首次执行和 completed replay。History 详情/更新/删除/两种导出另由上面的临时 API 合约检查验证。

## 未运行项目及原因

- 未使用真实 DeepSeek/API 凭据运行 provider acceptance 或真实 LLM 测试；这会引入外部服务和凭据风险，离线 fixture、mock、fallback 和完整回归已运行。
- 未重新运行 Java Maven 生产候选测试；本切片没有修改 Java、normalization client 或相关配置，现有后端 Java compatibility 测试包含在 555 测试全套中。
- 未部署生产、未连接生产数据库、未创建 tag/Release；用户明确禁止这些动作。
- GitHub CI 需在推送 PR 后由 GitHub 执行，不能由本地命令替代。

## 兼容性结论

- API：路径、方法、状态码、JSON shape、错误处理和关键响应头未改 handler；路由清单和中间件顺序保持一致。
- 数据库：未修改 Schema、Alembic revision、历史表或生产数据；`current/head` 均保持 `20260730_07`。
- 配置：未修改环境变量名称、默认行为或配置读取内容；本切片只改变 ASGI 入口调用关系。
- Java：normalization-only 服务、fallback、shadow/authoritative 规则未修改。
- Redis：未修改连接、缓存或 broker 行为。
- Worker/Outbox/Agent Run：未删除、迁移或改变生产 Compose 拓扑和历史用户可见能力。
- 前端：页面、文字、表单、响应式布局和主要视觉效果未修改。

## 已知风险与第二阶段建议

已知风险是仓库仍处于 transitional architecture：`legacy_application.py` 和 `legacy-workspace.jsx` 依然较大，且 `main.py` 仍需保留少量显式兼容导出。无法仅凭引用搜索证明安全删除的 legacy、Provider fallback、历史 Agent Run、Java、Redis、Worker、Outbox 和历史表均保留。

第二阶段应按单一领域逐个切片：先为 Analyze/Provider 建立 API snapshot 和 service 边界，再处理 History/Project Knowledge/Monitoring；之后才考虑 Resume 解析和配置入口的去重，最后拆分前端页面。每个切片都应复用现有测试、路由清单和 Compose smoke，避免同时改变挂载顺序或状态机。

## 回滚方法

实现代码可用以下可审查、可恢复的提交操作回滚：

```bash
git revert 91be64aeff50229d1cd4e60a451df6d42e7168a0
```

这只回滚本阶段的两个应用入口文件；没有生产部署或生产数据变更需要恢复。文档提交可单独按其 SHA 回滚，不影响运行时代码。

本报告没有写入密钥、Cookie、Resume/JD 内容、Provider 原始响应或生产用户数据；测试数据均为临时合成值。
