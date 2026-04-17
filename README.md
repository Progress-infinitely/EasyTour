# EasyTour — 旅游知识库 RAG 系统

基于 FastAPI + Milvus + MongoDB + DashScope 构建的旅游垂直知识库，支持文档导入、多意图查询、结构化答案与引用溯源。

---

## 技术栈

| 层 | 技术 |
|----|------|
| API | FastAPI + SSE 流式输出 |
| 向量库 | Milvus 2.4+（dense COSINE + sparse IP 混合检索） |
| 文档存储 | MongoDB（对话历史 / 检索 trace / 文档元数据 / alias 字典） |
| 对象存储 | MinIO（可选，原始文件归档） |
| LLM / Embedding / Rerank | DashScope（阿里云） |
| PDF 解析 | MinerU |
| 前端 | 静态 HTML（import.html / chat.html） |

---

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填写 DASHSCOPE_API_KEY / MONGO_URL 等

# 3. 启动服务
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：
- 文档导入页面：`http://localhost:8000/import.html`
- 对话页面：`http://localhost:8000/chat.html`
- 健康检查：`http://localhost:8000/healthz`

---

## 核心功能

### 文档导入（`/upload`）

- 支持 PDF / Markdown 上传
- 可选 override 参数：`content_type` / `region` / `document_title`
- 自动 LLM 抽取：内容类型、省市、主体名称、chunk 级结构化字段
- 文件去重（基于 sha256 内容哈希），支持三种模式：

| `force` 参数 | 行为 |
|-------------|------|
| 不传 | 同文件直接返回 `already_imported` |
| `metadata_only` | 仅更新地区/标题等文档级元数据，不重嵌入 |
| `reindex` | 完整重跑导入链，带回滚保护 |

### 查询（`/query`）

- 双意图识别：`retrieval_type`（内容类型过滤）+ `answer_intent`（回答模板选择）
- 支持 6 类内容类型：attraction / route / hotel / food / transport / culture
- 支持 6 类任务意图：lookup / recommendation / planning / comparison / howto / generic
- Alias 解析：将查询中的别名自动归一到 canonical 名称
- 结构化答案：按 `answer_intent` 返回不同 `structured` 字段（facts / recommendations / itinerary 等）
- Citation 溯源：每条答案附带来源标签（不含本地路径）
- 流式输出（SSE）

### 元数据接口

| 接口 | 说明 |
|------|------|
| `GET /meta/content_types` | 内容类型枚举 |
| `GET /meta/regions` | 已入库地区列表 |
| `GET /meta/items` | 已入库主体名列表 |
| `GET /documents/{document_id}` | 查询文档导入元数据 |
| `GET /healthz` | 依赖连通状态 |

---

## 数据模型

### Milvus Collection：`tour_chunks_v1`

热过滤字段（显式 schema）：`document_id` / `content_type` / `primary_item_name` / `province` / `city` / `region_path` / `chunk_hash` / `ingest_batch_id` / `created_at`

展示字段（dynamic field）：`entity_names` / `tips` / `notes` / `opening_hours` / `ticket_price` / `best_season` / `suitable_for` / `attraction_features` / `route_days` / `route_budget` / `price_range` / `hotel_tags` / `food_tags`

### MongoDB 集合

| 集合 | 用途 |
|------|------|
| `chat_message` | 对话历史 |
| `documents` | 文档元数据 + chunks_snapshot（用于 metadata_only / reindex 回滚） |
| `entity_aliases` | 别名字典（alias → canonical name） |
| `retrieval_trace` | 检索调试日志（topk / scores / expr / latency） |

---

## 测试

```bash
# 单元测试（无需运行服务）
python -m pytest tests/ -v --ignore=tests/test_integration_e2e.py

# 集成测试（需服务运行在 localhost:8000）
python -m pytest tests/test_integration_e2e.py -v -s
```

当前测试覆盖：
- `test_utils.py` — region_normalizer / hashing / build_milvus_expr / boost_by_entity_hit
- `test_import_nodes.py` — doc_level_extract_node / chunk_level_extract_node / entity_names
- `test_services.py` — DocumentService / TraceService / API 端点
- `test_query_graph_*.py` — 查询图节点行为 / 并行检索 / 语义一致性
- `test_integration_e2e.py` — 端到端上传/查询/判重/metadata_only/citations

---

## 环境变量（`.env.example`）

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key |
| `MONGO_URL` | MongoDB 连接串，如 `mongodb://admin:123456@127.0.0.1:27017` |
| `MONGO_DB_NAME` | 数据库名，默认 `easytour` |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 地址 |
| `CHUNKS_COLLECTION` | chunks 集合名，默认 `tour_chunks_v1` |
| `ITEM_NAME_COLLECTION` | 主体名集合名，默认 `tour_item_names_v1` |
| `REBUILD_MILVUS_COLLECTION` | `true` 时启动时 drop 重建（开发用） |
| `ENABLE_WEB_SEARCH` | 默认 `true`，开启 Web 补充检索 |
