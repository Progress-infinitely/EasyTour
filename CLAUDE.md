# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

EasyTour 是旅游垂直领域的 RAG 知识库系统，核心流程：文档导入 → 语义检索 → 意图驱动结构化答案 + 引用溯源。

## 常用命令

```bash
# 启动开发服务
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000 --reload

# 单元测试（无需运行服务）
python -m pytest tests/ -v --ignore=tests/test_integration_e2e.py

# 集成测试（需服务运行在 localhost:8000）
python -m pytest tests/test_integration_e2e.py -v -s

# 安装依赖
pip install -r requirements.txt

# 配置环境
cp .env.example .env  # 然后填写 DASHSCOPE_API_KEY / MONGO_URL 等
```

服务地址：导入页 `/import.html`、对话页 `/chat.html`、健康检查 `/healthz`、API 文档 `/docs`

## 架构

项目采用 **LangGraph 驱动的节点化流式处理**架构，核心在 `processor/` 下两个处理图：

### 导入流 (`processor/import_process/`)
```
Entry → File Hash → PDF→MD → Image Processing → Doc-level Extract →
Text Split → Embedding → Chunk-level Extract
```
- MinerU 做 PDF→Markdown，SHA256 做内容去重
- 三种 force 模式：默认（同文件跳过）/ metadata_only（仅更新元数据）/ reindex（完整重跑+回滚）

### 查询流 (`processor/query_process/`)
```
Intent Route → Alias Resolver → Item Name Confirm →
  ├→ Vector Search ─┐
  ├→ HyDE Search ──┼→ RRF Fusion → Rerank → Structured Answer
  └→ MCP Search ────┘
```
- 双意图：`retrieval_type`（attraction/route/hotel/food/transport/culture）+ `answer_intent`（lookup/recommendation/planning/comparison/howto/generic）
- 并行检索后 RRF 融合 + entity-aware boosting，再 QA rerank
- 按 answer_intent 选不同结构化模板生成答案，附带 citation 溯源

### 模块职责

| 模块 | 职责 |
|------|------|
| `api/main.py` | FastAPI 路由、SSE 流式输出、静态资源托管 |
| `processor/*/main_graph.py` | LangGraph 图编排 |
| `processor/*/nodes/` | 各处理步骤的独立 Node 实现 |
| `processor/*/config.py` | 每条链的参数配置（env → Python 字段） |
| `processor/*/state.py` | 图内状态流转的 Pydantic 模型 |
| `services/` | 业务逻辑抽象层（DocumentService、QueryService 等） |
| `schema/` | 全流程 Pydantic 数据模型，类型契约 |
| `utils/` | Milvus/MongoDB/MinIO 客户端、LLM Provider、region_normalizer 等 |
| `core/deps.py` | 依赖注入，管理 Service 生命周期 |
| `prompts/` | LLM prompt 模板（upload/ 和 query/） |

## 开发公约

- **节点化开发**：所有核心处理步骤必须封装在 `processor/*/nodes/` 下，通过 LangGraph 编排，不要把处理逻辑直接写在 API 或 Service 层
- **类型契约**：请求/响应/内部状态必须在 `schema/` 中定义 Pydantic 模型
- **依赖注入**：用 `core/deps.py` 管理 Service 生命周期，API 层不直接实例化重量级对象
- **向量检索**：默认 Dense (COSINE) + Sparse (IP) 混合检索，修改 Milvus Schema 时需同步更新 `utils/milvus_util.py`
- **修改处理流时**：优先检查对应 `main_graph.py` 和 `state.py`，确保状态流转一致性

## 关键数据模型

- **Milvus**：`tour_chunks_v1` — 热过滤字段（content_type/province/city 等）+ dynamic 展示字段（opening_hours/ticket_price 等）
- **MongoDB**：`documents`（元数据+chunks_snapshot）、`entity_aliases`（别名→标准名）、`chat_message`、`retrieval_trace`

## 环境变量要点

配置链路：`.env.example` → `.env` → `processor/*/config.py` → 具体节点逻辑

关键变量：`DASHSCOPE_API_KEY`（LLM/Embedding/Rerank 凭证）、`MONGO_URL`、`MILVUS_URL`、`MINERU_API_KEY`（PDF 解析）、`ENABLE_WEB_SEARCH` / `ENABLE_HYDE` / `ENABLE_RERANK`（功能开关）