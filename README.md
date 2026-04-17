# 掌柜智库 RAG 学习版

这是一个**给新手学习用的 RAG 项目**。

你可以先把它理解成一句话：

> 把 PDF / Markdown 文档导入知识库，再让系统基于知识库内容回答问题。

这个仓库的目标不是炫技，而是让你能顺着源码真正看懂：
- 一个 RAG 项目怎么分层
- 文件导入链怎么跑
- 问答链怎么跑
- 为什么要有向量库、对象存储、聊天历史、任务状态这些组件

---

## 0. 最适合小白的学习顺序

如果你想把学习曲线压到最低，推荐按下面这个顺序来：

### 第一遍：先建立全局地图
先读这些：
1. `README.md`
2. `.env.example`
3. `.env`
4. `easytour/processor/import_process/config.py`
5. `easytour/processor/query_process/config.py`

这一遍的目标不是记代码，而是先知道：
- 项目依赖哪些服务
- 两条主链分别做什么
- 关键配置项控制哪类行为

### 第二遍：再看接口和数据结构
再读这些：
1. `easytour/schema/*.py`
2. `easytour/api/main.py`
3. `easytour/services/import_file_service.py`
4. `easytour/services/query_service.py`

这一遍的目标是搞清楚：
- 前端和后端到底传什么数据
- 请求从哪里进来
- task_id / session_id / history / stream 是怎么串起来的

### 第三遍：再看流程编排
再读这些：
1. `easytour/processor/import_process/main_graph.py`
2. `easytour/processor/query_process/main_graph.py`
3. `easytour/processor/*/state.py`
4. `easytour/processor/*/base.py`

这一遍的目标是搞清楚：
- 导入链顺序是什么
- 查询链顺序是什么
- 节点之间靠什么传数据

### 第四遍：最后钻具体节点
按导入链和查询链分别往下看 `nodes/*.py`。

### 第一遍先别深究这些
如果你是第一次看源码，下面这些先不要一上来就钻进去：
- `docs/**/hybrid_auto/*`
- 各种生成产物
- 太底层的 SDK 细节
- 细碎的工具函数实现

先抓主干，再补细节，会轻松很多。

---

## 1. 这个项目到底在做什么？

项目主要有两条主链：

### 1.1 导入链

作用：
把一个 PDF 或 Markdown 文档，处理成“可以被检索”的知识数据。

导入链的大致流程：

`上传文件`
→ `判断文件类型`
→ `如果是 PDF，就先转成 Markdown`
→ `处理 Markdown 里的图片`
→ `把长文切成小块（chunks）`
→ `识别这份文档主要讲的是哪个设备/商品`
→ `给每个 chunk 生成向量`
→ `写入 Milvus`

### 1.2 查询链

作用：
用户提一个问题，系统先去知识库里找材料，再组织出最终答案。

查询链的大致流程：

`识别问题主体`
→ `普通向量检索`
→ `HyDE 检索`
→ `可选的联网搜索`
→ `多路结果融合`
→ `精排`
→ `大模型生成答案`

---

## 2. 先给完全小白的几个核心概念

如果你是第一次学这类项目，下面这些词先知道大概意思就够了。

### RAG 是什么？

RAG = Retrieval-Augmented Generation。

你可以把它理解成：

- **Retrieval（检索）**：先去知识库里找资料
- **Generation（生成）**：再让大模型基于资料回答

也就是说，模型不是纯靠“脑补”回答，而是先查资料再说话。

### chunk 是什么？

chunk 就是把一整份长文，切成很多个较小的文本块。

为什么要切？
因为：
- 整本文档太长，不适合直接拿去做检索
- 用户的问题通常只和其中某几段有关
- 切小之后，更容易找到真正相关的内容

### embedding 是什么？

embedding 可以理解成：
**把一段文本变成向量数字**。

这样系统就能用“向量相似度”去判断：
- 用户问题和哪些文本块更像
- 哪些 chunk 更可能相关

### 向量库是什么？

这个项目里用的是 **Milvus**。

它的作用是：
**专门存向量，并支持相似度检索。**

简单说：
普通数据库擅长查“完全匹配”；
向量库擅长查“语义相近”。

### LangGraph 是什么？

你可以先把它理解成：
**用来编排流程节点的工具。**

比如：
- 第一步做什么
- 第二步做什么
- 某种条件下走哪条分支

在这个项目里：
- 导入链是一张 graph
- 查询链也是一张 graph

### SSE 是什么？

SSE = Server-Sent Events。

你可以把它理解成：
**后端不断往前端推消息。**

这里主要用于：
- 实时推送查询进度
- 流式推送模型输出文本

注意：这里说的 SSE 是项目自己给前端做流式推送的浏览器协议，
不是百炼 WebSearch MCP 之前使用过的旧版 transport。
当前项目里的 MCP 联网搜索已经使用 Streamable HTTP。

### HyDE 是什么？

HyDE 是一种检索增强思路。

简单理解：
- 先让模型根据问题“脑补一段像说明书的文字”
- 再拿这段文字去检索

它的作用是：
当用户问题太短时，帮助检索拿回更多可能相关的文档块。

### RRF 是什么？

RRF = Reciprocal Rank Fusion。

你可以把它理解成：
**把多路检索结果合并排序。**

比如：
- 普通向量检索找到一些结果
- HyDE 检索又找到一些结果
- RRF 负责把它们融合成一份更稳的候选列表

### rerank 是什么？

rerank = 重排 / 精排。

意思是：
系统先粗略找回一批“可能相关”的文档，
再用专门的模型重新判断“谁最相关”，把顺序排得更准确。

---

## 3. 这个项目的整体架构怎么理解？

先记一句最重要的话：

> 这个项目是“本地编排 + 远程模型能力”的 RAG 项目。

### 3.1 本地保留了什么？

本地主要保留中间件和编排逻辑：

- **FastAPI**：提供 HTTP 接口和页面
- **Milvus**：存向量和做检索
- **MinIO**：存文件和图片
- **Mongo**：存聊天历史
- **LangGraph**：组织导入链和查询链

### 3.2 高算力部分放在哪里？

高算力能力都改成远程 API：

- **MinerU**：远程 PDF 解析
- **Embedding**：远程向量化
- **Rerank**：远程精排
- **LLM / VLM**：远程大模型调用
- **WebSearch MCP**：远程联网搜索

### 3.3 为什么这样设计？

因为这样更适合学习项目：

- 本地环境更轻
- 不用自己在本地部署大模型
- 可以把注意力放在“项目结构和流程”上
- 更容易理解每一层到底负责什么

---

## 4. 目录怎么读？

### `easytour/api`

HTTP 接口层。

重点文件：
- `easytour/api/main.py`

作用：
- 创建 FastAPI 应用
- 注册导入接口、查询接口、状态接口
- 挂载前端静态页面

### `easytour/core`

基础依赖和路径工具。

重点文件：
- `easytour/core/deps.py`
- `easytour/core/paths.py`

作用：
- 管理 service 的依赖注入
- 统一管理项目关键目录路径

### `easytour/services`

业务调度层。

重点文件：
- `easytour/services/import_file_service.py`
- `easytour/services/query_service.py`
- `easytour/services/task_service.py`

作用：
- 接 API 层请求
- 生成 task_id / session_id
- 调 graph
- 维护任务状态
- 保存历史记录

### `easytour/processor/import_process`

导入链。

重点文件：
- `main_graph.py`：定义导入主流程
- `state.py`：定义导入链共享状态
- `base.py`：定义导入节点公共行为
- `nodes/*.py`：每个具体节点

### `easytour/processor/query_process`

查询链。

重点文件：
- `main_graph.py`：定义查询主流程
- `state.py`：定义查询链共享状态
- `base.py`：定义查询节点公共行为
- `nodes/*.py`：每个具体节点

### `easytour/utils`

基础工具层。

你可以把这里理解成“被很多地方复用的底层工具”。

比如：
- `http_client.py`：统一 HTTP 请求
- `task_util.py`：任务状态看板
- `sse_util.py`：流式推送
- `mongo_history_util.py`：聊天历史存取
- `providers/*.py`：远程模型适配层
- `client/*.py`：基础客户端管理层

### `easytour/front`

前端静态页面。

重点文件：
- `chat.html`
- `import.html`

### `docs`

这里主要放测试用或学习用文档。

注意：
- `docs/*.pdf` 是原始资料
- `docs/**/hybrid_auto/*` 往往是导入过程生成出来的产物
- 这些不是你一开始读源码的重点

---

## 5. 运行前要准备什么？

### 5.1 Python 环境

推荐先在项目目录创建并激活虚拟环境。

Windows PowerShell 示例：

```powershell
cd E:\SGG_AI\Practice_Code\RAG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果你已经有可复用的 Python 环境，也可以直接使用，但**README 下面所有命令都默认你站在当前仓库目录里运行**。

### 5.2 本地中间件

项目启动前，请先保证这些服务可用：

- Milvus
- MinIO
- Mongo

它们的作用分别是：
- Milvus：存向量
- MinIO：存文件/图片
- Mongo：存聊天历史

### 5.3 环境变量

请参考仓库里的：

- `.env.example`

建议做法：
1. 复制一份 `.env.example` 为 `.env`
2. 再按你自己的环境补齐配置

最关键的环境变量如下。

#### A. 大模型 / 兼容接口

- `OPENAI_API_KEY`
  - 远程模型服务的密钥
- `OPENAI_API_BASE`
  - 远程模型服务地址
- `LLM_DEFAULT_MODEL`
  - 默认文本模型名
- `VL_MODEL`
  - 视觉模型名，用于图片摘要

#### B. MinerU（PDF 转 Markdown）

- `MINERU_API_KEY`
- `MINERU_API_BASE`
- `MINERU_MODEL_VERSION`

如果你要导入 PDF，这组配置很重要。
如果你只导入现成 Markdown，可以暂时不依赖这一组。

#### C. Embedding / Rerank

- `EMBEDDING_MODEL=text-embedding-v4`
- `EMBEDDING_DIM=1024`
- `RERANK_MODEL=qwen3-rerank`

#### D. Milvus

- `MILVUS_URL`
- `CHUNKS_COLLECTION`
- `ITEM_NAME_COLLECTION`

如果集合名不配，项目也可能自动创建，但你最好知道自己现在在写哪个集合。

#### E. MinIO

- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET_NAME`
- `MINIO_SECURE`

#### F. Mongo

- `MONGO_URL`
- `MONGO_DB_NAME`

#### G. 联网搜索（可选增强）

- `ENABLE_WEB_SEARCH=true`
  - 启用后，查询链会额外调用百炼 WebSearch MCP 做公网信息补充
- `MCP_DASHSCOPE_BASE_URL`
  - 使用 `/mcp` 结尾的 Streamable HTTP 地址
  - 示例：`https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp`

如果这组没配好，项目主问答仍然可以跑，只是联网搜索那一路会降级为空结果。

---

## 6. 最短启动步骤

### 6.1 安装依赖

```powershell
cd E:\SGG_AI\Practice_Code\RAG
python -m pip install -r requirements.txt
```

### 6.2 启动服务

方式一：直接用模块启动

```powershell
cd E:\SGG_AI\Practice_Code\RAG
python -m easytour.api.main
```

方式二：用 uvicorn 启动

```powershell
cd E:\SGG_AI\Practice_Code\RAG
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000
```

默认地址：

- `http://127.0.0.1:8000`

### 6.3 打开页面

服务启动后，常用入口：

- 导入页：`http://127.0.0.1:8000/import`
- 聊天页：`http://127.0.0.1:8000/chat.html`
- 健康检查：`http://127.0.0.1:8000/healthz`
- API 文档：`http://127.0.0.1:8000/docs`

---

## 7. 最小联调流程（照着走一遍就能确认项目基本通了）

### 7.1 先测服务有没有活着

浏览器打开：

- `http://127.0.0.1:8000/healthz`

正常返回：

```json
{"status":"ok"}
```

### 7.2 测一次导入

去导入页上传一个 PDF。

推荐直接用：

- `docs/H3C LA2608室内无线网关 用户手册-6W100-整本手册.pdf`

上传后页面通常会显示：

- 当前状态
- 已完成节点
- 正在运行节点
- `file_title`
- `item_name`
- `chunk_count`

如果你想手动查状态：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status/<task_id>" -Method Get
```

这里的 `<task_id>`，就是上传接口返回给你的任务编号。

### 7.3 测一次查询

导入完成后，去聊天页提问，例如：

- `LA2608 是什么设备？`
- `H3C LA2608 官网怎么描述？`
- `最近公开资料里 LA2608 有哪些信息？`

如果你想直接调接口：

```powershell
$body = @{
  query = "LA2608 是什么设备？"
  session_id = "demo-session"
  is_stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/query" -Method Post -ContentType "application/json" -Body $body
```

查询历史：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/history/demo-session" -Method Get
```

如果你想体验流式：
- 发起 `/query` 时把 `is_stream` 设成 `true`
- 然后前端或脚本去订阅 `/stream/{task_id}`

---

## 8. 为什么查询链不是只做一次检索？

因为真实问题常常不稳定：
- 用户问题很短
- 用户说简称、代词、型号
- 单一路径容易漏召回

所以这里用了多路召回：

### 8.1 普通向量检索

最基础的一路。

做法：
- 把问题转成向量
- 去 Milvus 的 chunk 集合里找最相近的内容

### 8.2 HyDE 检索

做法：
- 先让模型写一段“像说明书正文”的假想内容
- 再拿这段内容去检索

优点：
- 对短问题更友好
- 经常能召回普通向量检索漏掉的片段

### 8.3 WebSearch MCP

做法：
- 通过 Streamable HTTP 调远程百炼 WebSearch MCP
- 补充知识库之外的公开网页信息
- MCP 地址由 `MCP_DASHSCOPE_BASE_URL` 控制，推荐使用 `/mcp` 结尾地址

注意：
它是增强链路，不是唯一依赖。
就算联网搜索挂了，系统仍然可以只靠知识库回答。

### 8.4 RRF 融合

作用：
把多路结果合成一份统一候选列表。

### 8.5 rerank 精排

作用：
对候选结果重新打分，把真正最相关的文档放到前面。

---

## 9. 推荐你按什么顺序读源码？

如果你一上来就钻进某个复杂节点，大概率会晕。
正确顺序应该是：

### 第一层：先看入口（）

1. `easytour/api/main.py`
2. `easytour/core/deps.py`
3. `easytour/core/paths.py`

先知道：
- 服务是怎么启动的
- 路由有哪些
- service 是怎么被注入进来的

### 第二层：再看 service 层（）

4. `easytour/services/import_file_service.py`
5. `easytour/services/query_service.py`
6. `easytour/services/task_service.py`

先知道：
- API 收到请求后，真正把任务交给了谁
- task_id / session_id 是怎么来的
- 历史记录和任务状态是怎么维护的

### 第三层：再看两张主图

7. `easytour/processor/import_process/main_graph.py`
8. `easytour/processor/query_process/main_graph.py`

先知道：
- 导入链整体顺序是什么
- 查询链整体顺序是什么
- 哪些地方有分支

### 第四层：看 state 和 base

9. `easytour/processor/import_process/state.py`
10. `easytour/processor/query_process/state.py`
11. `easytour/processor/import_process/base.py`
12. `easytour/processor/query_process/base.py`

先知道：
- 节点之间靠什么传数据
- 为什么所有节点都长得很像
- 为什么它们都能自动更新任务状态和日志

### 第五层：最后再看具体节点

#### 导入链重点节点

- `easytour/processor/import_process/nodes/entry_node.py`
- `easytour/processor/import_process/nodes/pdf_to_md_node.py`
- `easytour/processor/import_process/nodes/md_img_node.py`
- `easytour/processor/import_process/nodes/document_split_node.py`
- `easytour/processor/import_process/nodes/item_name_recognition_node.py`
- `easytour/processor/import_process/nodes/bge_embedding_chunks_node.py`
- `easytour/processor/import_process/nodes/import_milvus_node.py`

#### 查询链重点节点

- `easytour/processor/query_process/nodes/item_name_confirm_node.py`
- `easytour/processor/query_process/nodes/vector_search_node.py`
- `easytour/processor/query_process/nodes/hyde_search_node.py`
- `easytour/processor/query_process/nodes/mcp_search_node.py`
- `easytour/processor/query_process/nodes/rrf_node.py`
- `easytour/processor/query_process/nodes/rerank_node.py`
- `easytour/processor/query_process/nodes/answer_output_node.py`
- `easytour/processor/query_process/nodes/common.py`

### 第六层：最后再看基础设施工具

- `easytour/utils/http_client.py`
- `easytour/utils/task_util.py`
- `easytour/utils/sse_util.py`
- `easytour/utils/mongo_history_util.py`
- `easytour/utils/providers/*.py`
- `easytour/utils/client/*.py`

---

## 10. 哪些文件最值得重点理解？

如果你时间不多，只想先抓主干，优先看这些：

### 服务入口

- `easytour/api/main.py`
- `easytour/core/deps.py`
- `easytour/core/paths.py`

### 服务层

- `easytour/services/import_file_service.py`
- `easytour/services/query_service.py`
- `easytour/services/task_service.py`

### 导入链

- `easytour/processor/import_process/main_graph.py`
- `easytour/processor/import_process/state.py`
- `easytour/processor/import_process/nodes/document_split_node.py`
- `easytour/processor/import_process/nodes/pdf_to_md_node.py`
- `easytour/processor/import_process/nodes/import_milvus_node.py`

### 查询链

- `easytour/processor/query_process/main_graph.py`
- `easytour/processor/query_process/state.py`
- `easytour/processor/query_process/nodes/item_name_confirm_node.py`
- `easytour/processor/query_process/nodes/vector_search_node.py`
- `easytour/processor/query_process/nodes/rerank_node.py`
- `easytour/processor/query_process/nodes/answer_output_node.py`

### 基础设施

- `easytour/utils/http_client.py`
- `easytour/utils/task_util.py`
- `easytour/utils/sse_util.py`
- `easytour/utils/providers/provider_factory.py`
- `easytour/utils/client/storage_clients.py`
- `easytour/utils/mongo_history_util.py`

---

## 11. 常见问题（小白最容易卡住的地方）

### Q1：为什么 state 要设计成一个大字典？

因为 LangGraph 的节点之间，本质上就是靠 state 传数据。

你可以把它理解成：
**流水线上的共享工作单。**

- 前一个节点把结果写进去
- 后一个节点继续拿出来用

### Q2：为什么既有 service，又有 graph？

因为它们不是一层东西。

- **service**：面向 HTTP 请求，负责接接口、生成 task_id、保存历史、管理流式/非流式
- **graph**：面向流程编排，负责定义节点先后顺序和分支路线

### Q3：为什么查询链里先做主体名称确认？

因为用户常常不会老老实实说完整商品名。

例如：
- 只说型号
- 用简称
- 用“它”“这个设备”指代

先把主体确认出来，后面的检索更准。

### Q4：为什么还要保留 Milvus / MinIO / Mongo 的本地部署？

因为它们不是高算力模型，而是中间件。

职责分别是：
- Milvus：存向量
- MinIO：存文件/图片
- Mongo：存聊天历史

### Q5：为什么查询链里还要 rerank？

因为召回出来的内容只是“可能相关”，顺序未必最好。

rerank 的作用是：
**再精排一次，把最相关的内容放前面。**

### Q6：为什么 WebSearch 挂了系统还能回答？

因为 WebSearch 是增强链路，不是主链唯一来源。

就算联网搜索不可用：
- 本地知识库检索
- HyDE 检索
- rerank
- 最终回答生成

这些仍然可以工作。

### Q7：为什么服务重启后，有些任务状态会没了？

因为任务状态是存在进程内内存里的。

这是一种“学习项目优先简单实现”的做法。

但聊天历史不是靠这个保存的，聊天历史走的是 Mongo（或内存降级）。

### Q8：如果导入 PDF 失败，最先该看哪里？

优先检查：
1. `MINERU_API_KEY` 是否配置
2. `MINERU_API_BASE` 是否正确
3. 远程 API 是否可访问
4. `easytour/processor/import_process/nodes/pdf_to_md_node.py` 的日志输出

### Q9：如果查询没有结果，最先该看哪里？

优先检查：
1. 文档是否真的导入成功
2. `chunk_count` 是否大于 0
3. Milvus 集合里是否有数据
4. `item_name` 是否识别过严
5. `vector_search_node.py` / `item_name_confirm_node.py` 的日志和状态

---

## 12. 当前这个仓库最适合拿来学什么？

如果你的目标是“照着学一个完整 RAG 项目的骨架”，这个仓库非常适合练这几件事：

- API 层怎么接请求
- service 层怎么调度
- graph 怎么做流程编排
- state 怎么在节点之间流动
- 向量检索、融合、精排怎么串起来
- 流式回答和任务状态怎么实现
- provider / client / utility 这些基础层怎么分层

---

## 13. 一句话总结这个项目

如果你现在只想记一句话，那就记这个：

> 这是一个“文档导入 + 知识问答”的学习型 RAG 项目，核心价值在于让你看懂完整流程，而不是只会调用几个模型 API。
