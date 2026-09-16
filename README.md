# Riton Interview Backend

面试辅助后端，提供简历分析、知识库检索、文本/语音面试、面试日程和 LLM Provider 管理 API。

## 一键启动

前置条件：Docker 20.10+、Docker Compose v2+，建议为 Docker 分配至少 4 GB 内存。首次启动需要下载约数 GB 的镜像和 Python 依赖。

```bash
docker compose up -d --build
docker compose ps
```

服务就绪后：

- 前端：`http://localhost`（通过 `FRONTEND_PORT` 修改宿主机端口）
- 后端 API：`http://localhost:8072`
- OpenAPI 文档：`http://localhost:8072/docs`
- 健康检查：`http://localhost:8072/health`
- RustFS 控制台：`http://localhost:9001`
- Elasticsearch：`http://localhost:9200`

Compose 会构建 `frontend/` 中的前端镜像。浏览器以同源方式访问 `/api` 和 `/ws`，前端 Nginx 在 Docker 网络内将请求转发到 `backend:8072`。本地运行 Vite 时，开发代理默认连接 `http://localhost:8072`，可通过 `VITE_API_PROXY_TARGET` 覆盖。

如需自定义端口、密码或第三方模型服务：

```bash
copy .env.example .env
docker compose up -d --build
```

Linux/macOS 使用 `cp .env.example .env`。`.env` 已被 Git 忽略，请勿提交真实密钥。

## 服务和版本

| 服务 | Compose 版本 | 容器内地址 | 宿主机默认地址 |
| --- | --- | --- | --- |
| Frontend | Node.js 20 + Nginx | `frontend:80` | `http://localhost` |
| Backend | Python 3.13 | - | `http://localhost:8072` |
| MySQL | 8.4.10 | `mysql:3306` | `localhost:3308` |
| Elasticsearch | 8.19.17 | `elasticsearch:9200` | `localhost:9200` |
| RocketMQ Proxy | 5.3.4 | `rocketmq-proxy:8081` | `localhost:8081` |
| RocketMQ Broker | 5.3.4 | `rocketmq-broker:10911` | `localhost:10911` |
| RocketMQ NameServer | 5.3.4 | `rocketmq-nameserver:9876` | `localhost:9876` |
| RustFS | 1.0.0-beta.11 | `rustfs:9000` | `localhost:9000` |

RocketMQ Python 客户端为 `rocketmq-python-client==5.1.1`，它使用 RocketMQ 5.x Proxy 的 gRPC 端口 `8081`，不是旧客户端直连 NameServer 的方式。NameServer、Broker 和 Proxy 分别运行；Proxy 使用 Cluster 模式，并在 Broker 健康后启动。

全部服务都显式加入 `${COMPOSE_NETWORK_NAME:-interview-network}` bridge 网络。Broker 不再向 NameServer 注册 `127.0.0.1`，避免独立 Proxy 把 Broker 地址错误解析为自己的回环地址。

Elasticsearch 以单节点开发模式运行并关闭了认证，仅适合本机或受信网络。RustFS 当前仍为 beta 版本；生产环境应评估多副本、TLS、备份和密钥管理。

基础设施端口默认只绑定 `127.0.0.1`，后端默认绑定 `0.0.0.0`。可分别通过 `INFRA_BIND_ADDRESS` 和 `BACKEND_BIND_ADDRESS` 调整。`rocketmq-permissions` 与 `rustfs-permissions` 是初始化命名卷权限的一次性容器，显示为 `Exited (0)` 属于正常状态。

## 数据库初始化

所有业务表和开发过程中出现的 `ALTER TABLE` 补丁已经合并到 `resources/sql/init_schema.sql`。MySQL 首次创建数据卷时会执行这一个文件：

- 创建 `interview` 业务数据库及全部 16 张业务表；
- 创建 `checkpointer` 数据库，LangGraph 启动时自动创建自己的 checkpoint 表；
- 不再执行历史 migration 文件。

MySQL 官方镜像只会在空数据目录执行 `/docker-entrypoint-initdb.d`。修改初始化 SQL 后若要重新验证全新安装，需要先备份数据，再显式删除数据卷；`docker compose down -v` 会永久删除本 Compose 的全部持久化数据。

## 外部服务配置

Compose 已把基础设施地址配置为 Docker 网络内的服务名：

| 环境变量 | Compose 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+aiomysql://...@mysql:3306/interview` | 业务数据库 |
| `DB_URI` | `mysql+aiomysql://...@mysql:3306/checkpointer` | LangGraph checkpoint 数据库 |
| `ROCKETMQ_ENDPOINTS` | `rocketmq-proxy:8081` | RocketMQ 5.x Proxy gRPC 地址 |
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | 向量检索服务 |
| `RUSTFS_ENDPOINT_URL` | `http://rustfs:9000` | S3-compatible 对象存储 |

若后端不在 Compose 网络内运行，把这些值改为宿主机或远端服务的可达地址。MySQL 密码出现在 URI 中时必须进行 URL 编码。

### LLM 和 Embedding

LLM Provider 模块支持 OpenAI-compatible Chat Completions 和 Embeddings 服务，可通过 Provider API 动态新增、测试、启停和切换默认 Provider。首次启动时 Compose 使用以下变量引导创建 `default` Provider：

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_CHAT_MODEL`
- `LLM_EMBEDDING_MODEL`
- `LLM_EMBEDDING_DIMENSIONS`
- `LLM_PROVIDER_ENCRYPTION_KEY`

默认 `LLM_API_KEY=replace-me` 只保证后端能够启动，实际调用模型前必须配置真实密钥。Bootstrap 仅在 Provider 表为空时执行；已有数据卷应通过 `/api/llm-provider` 接口更新配置。`LLM_PROVIDER_ENCRYPTION_KEY` 用于加密数据库中的 API Key，数据存在后不可随意更换。

### ASR 和 TTS

语音配置可以通过 `/api/llm-provider/voice/asr` 和 `/api/llm-provider/voice/tts` 动态更新，并持久化到数据库。当前代码的底层协议实现是 DashScope Realtime WebSocket，因此它不是任意供应商通用适配器：

- `VOICE_DASHSCOPE_API_KEY`：DashScope ASR/TTS 共用密钥；
- `VOICE_DASHSCOPE_REALTIME_URL`：默认 `wss://dashscope.aliyuncs.com/api-ws/v1/realtime`；
- ASR/TTS 模型、音色、采样率等可通过语音 Provider API 修改；
- 要接入非 DashScope 协议的供应商，需要实现 `AsrProvider` / `TtsProvider` 接口并在依赖装配中选择对应实现。

未配置语音密钥不会阻止后端启动，但语音 WebSocket 在实际调用时会返回配置错误。

## 依赖核对

`requirements.txt` 最初是环境冻结清单，后续只同步过 RocketMQ 5.x 客户端变更。当前核对结果：

- 生产代码的第三方直接 import 均有对应依赖；
- `rocketmq-python-client==5.1.1` 与当前 RocketMQ 5.x API 用法一致；
- 测试使用 `sqlite+aiosqlite`，原清单漏了 `aiosqlite`，现已补充；
- Docker 镜像额外安装 `libmagic1`，供 `python-magic` / `unstructured` 检测文件类型。

本地运行测试：

```bash
python -m pytest -q --basetemp=.pytest-tmp -p no:cacheprovider
```

## 常用运维命令

```bash
docker compose logs -f backend
docker compose logs -f rocketmq-proxy
docker compose ps
docker compose restart backend
docker compose down
```

生产部署前至少需要替换 MySQL/RustFS 密码、LLM 加密密钥和第三方 API Key，并为 Elasticsearch、RustFS、MySQL 与对外 API 配置认证、TLS、网络隔离和备份。
