# 🚀 EasyTour 项目指南

EasyTour 是一个专为旅游垂直领域设计的 **RAG（检索增强生成）知识库系统**。它通过集成 FastAPI、LangGraph、Milvus 和 MongoDB，实现了从原始文档（PDF/Markdown）到结构化知识提取、语义检索及意图驱动的智能回答的全链路功能。

---

## 🏗️ 系统架构

项目采用模块化设计，核心逻辑由 **LangGraph** 驱动的流式处理图（Process Graphs）承载：

### 1. 核心模块分布
- **`easytour/api`**: 系统入口，提供 FastAPI 路由、SSE 流式输出及静态资源托管。
- **`easytour/processor`**: 核心逻辑层，包含 `import_process`（文档入库流）和 `query_process`（查询处理流）。
- **`easytour/services`**: 业务逻辑抽象层，管理文档元数据、查询任务状态及历史追踪。
- **`easytour/utils`**: 基础设施适配层，封装了 Milvus、MongoDB、MinIO 及各类 LLM/Embedding Provider。
- **`easytour/schema`**: 定义了全流程使用的 Pydantic 数据模型，确保类型安全。

### 2. 处理流逻辑
- **导入流 (Import Graph)**: 
  `文件哈希` -> `文档级元数据提取` -> `文本切分` -> `Chunk 级结构化字段提取` -> `向量化与存储`。
- **查询流 (Query Graph)**: 
  `意图路由` -> `别名解析` -> `主体确认` -> `并行检索 (Vector + HyDe + MCP)` -> `RRF 融合` -> `Rerank 重排序` -> `结构化答案生成`。

---

## 🛠️ 开发与运行

### 1. 环境配置
1. 安装依赖：`pip install -r requirements.txt`
2. 基础环境：确保本地或远程拥有 Milvus 2.4+、MongoDB 4.4+ 及 MinIO 服务。
3. 变量配置：拷贝 `.env.example` 为 `.env` 并填写 `DASHSCOPE_API_KEY` 等关键凭据。

### 2. 启动服务
```bash
# 开发模式启动
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000 --reload
```
- **导入界面**: `http://localhost:8000/import.html`
- **对话界面**: `http://localhost:8000/chat.html`
- **API 文档**: `http://localhost:8000/docs`

### 3. 测试验证
- **单元测试**: `python -m pytest tests/ -v`
- **集成测试**: 需启动服务后运行 `python -m pytest tests/test_integration_e2e.py`

---

## 📝 核心开发公约

- **节点化开发**: 所有核心处理步骤必须封装在 `easytour/processor/.../nodes` 下的独立 Node 类中，并通过 LangGraph 进行编排。
- **类型契约**: 所有的接口请求、响应及内部状态传递（State）必须在 `easytour/schema` 中定义对应的 Pydantic 模型。
- **依赖注入**: 使用 `easytour/core/deps.py` 管理 Service 的生命周期，避免在 API 层直接实例化重量级对象。
- **向量检索**: 默认采用 **Dense (COSINE)** 与 **Sparse (IP)** 混合检索，修改 Schema 时需同步更新 `milvus_util.py`。

---

## 📂 关键文件索引

| 文件路径 | 描述 |
|:---|:---|
| `easytour/api/main.py` | API 路由定义与 SSE 生成逻辑 |
| `easytour/processor/import_process/main_graph.py` | 文档导入流编排 |
| `easytour/processor/query_process/main_graph.py` | 查询处理流编排 |
| `easytour/services/document_service.py` | 文档持久化与元数据管理核心逻辑 |
| `easytour/utils/milvus_util.py` | 向量数据库操作封装 |
| `.env.example` | 环境变量模板，定义了系统所需的外部依赖 |

---
💡 **提示**: 修改处理流程时，请优先检查对应的 `main_graph.py` 和 `state.py`，确保状态流转的一致性。
