# 旅游知识库系统 MVP 改造技术方案与实施设计说明书

> **工作目录**：`E:\SGG_AI\Practice_Code\EasyTour`
> **参考基线**：`E:\SGG_AI\Practice_Code\RAG`（代码包名 `knowledge`，下文统一简称 **DocNest**）
> **文档版本**：v2.2（在 v2.1 基础上修订：判重/纠错闭环 / Mongo env 口径 / 主体过滤策略 / alias 查询闭环）
> **本文档是后续所有开发的唯一执行依据，严禁与本文之外的口径并存**

---

## 0''. v2.2 修订摘要（本次修订）

| # | 项 | 问题 | 新口径 |
|---|----|------|--------|
| α | 判重响应 | task_id 是进程内存态，重启后原 task_id 不可查 | 判重命中时**不返回原 task_id**，只返回 `{document_id, status: "already_imported"}`；前端根据 document_id 查 `/documents/{id}` 而不是 `/status/{task_id}` |
| β | 判重 vs override 纠错 | 同文件重传想改 content_type/region 会被判重拦截，纠错链断 | 新增 **`force` 上传参数**（与 override 解耦）：`force=metadata_only` **仅允许文档级元数据纠错**（region/source/document_title 等，不改 chunk 结构）；若检测到 `content_type` 变化则拒绝并要求 `reindex`；`force=reindex` 改为**先离线重建、再带回滚提交**，默认不传则走判重短路 |
| γ | Mongo env 口径 | 方案写 `MONGO_DB`，基线用 `MONGO_DB_NAME`，易静默降级到内存 | **统一用基线口径**：`MONGO_URL` + `MONGO_DB_NAME`；services 启动时主动探测并在 /healthz 暴露 `mongo_connected` 布尔 |
| δ | 高置信主体过滤策略 | `primary_item_name == X` 会误杀多实体 chunk（如一日游线路） | 改成 **多字段 OR 宽过滤**：`(primary_item_name == X) OR (entity_names 包含 X 的 JSON_CONTAINS 表达式)`；实现上若 Milvus 版本不支持 JSON_CONTAINS 则回退为"只过 primary，entity_names 命中改走加权 + 提高加权系数" |
| ε | alias 查询闭环 | 别名只在导入端被消费，查询端没明确路径 | 新增 `alias_resolver`（内存 LRU + MongoDB `entity_aliases` 源）：intent_route 之后、item_name_confirm 之前把 query 中的 alias 映射为 canonical name；命中即把 canonical name 注入 rewritten_query 与后续主体确认入参 |

---

## 0'. v2.1 修订摘要

| # | 项 | 问题 | 新口径 |
|---|----|------|--------|
| A | document_id 定义 | 5.2 / 7.5 口径冲突 | **固定为 `file_hash[:16]`**，与 ingest_batch_id 解耦；去重只看 document_id |
| B | 首版抽取字段 | 需求要"适合人群/特色/tips/注意事项"，v2.0 首版不抽导致数据层断供 | chunk 级补抽 `suitable_for` / `attraction_features` / `tips` / `notes`（允许为空，不强制完整） |
| C | 查询过滤维度 | 只有 content_type + region，浪费 item_name_confirm | 新增"主体名加权"规则：高置信主体命中时 expr 追加 `primary_item_name == "X"`；未加 filter 时在 rerank 前做实体名加权 |
| D | entity_names 漏抽兜底 | 文档级漏 → chunk 级永远补不回 | chunk 级扫描标题/正文 H2/H3，命中未登记主体即加入 entity_names 临时表（无 LLM 调用） |

---

## 0. v2.0 修订摘要（相对 v1.0）

| # | 项 | v1.0 旧口径 | v2.0 新口径 |
|---|----|------------|------------|
| 1 | 上传接口元数据 | 口径矛盾（全 LLM / 表单 / 半自动） | **双轨制**：file 必填，content_type/region/source_path 可选 override |
| 2 | LLM 抽取分层 | 文档级 + chunk 级均抽大量字段 | **分层收敛**：全局字段只在文档级抽一次；chunk 级只抽少量局部字段 |
| 3 | Milvus 字段分层 | 业务字段大量塞 dynamic field | **热过滤字段必须显式 schema**，展示字段才进 dynamic field |
| 4 | region 存储 | 单一自由文本 + `like "%三亚%"` | 拆成 province / city / region_path，过滤走 `city == "三亚"` 或前缀匹配 |
| 5 | 主体字段 | 单一 item_name + tour_entities 兼容 | chunk 级 primary_item_name + entity_names，文档级 doc_main_entities |
| 6 | intent 模型 | intent 等同 content_type | 拆分为 retrieval_type（内容类型）+ answer_intent（任务意图） |
| 7 | 文档去重 | 无 | 新增 document_id / file_hash / chunk_hash / ingest_batch_id / created_at |
| 8 | aliases 存储 | VARCHAR + "|" 拼接 | Milvus 只存 canonical name，aliases 放 MongoDB |
| 9 | 检索调试持久化 | 未设计 | 增加 retrieval_trace 落库，含 topk、scores、filters、latency |
| 10 | source_path 回显 | 裸路径直接给前端 | 拆 source_uri_internal / source_label_display，前端只看后者 |
| 11 | 一致性矛盾 | schema/node/附录口径不一 | 全文所有模块统一引用本章节结论 |

---

## 1. 文档概述

### 1.1 目的
- 锁定 MVP 范围与架构取舍，避免开发过程需求发散
- 明确复用 DocNest 的哪些模块、必须改造哪些模块
- 给出数据模型、API、节点清单、分阶段计划

### 1.2 读者
- 开发者（本人）：按第 10-11 章逐步施工
- 未来扩展者：据第 5 章快速理解全貌
- AI 协作者：据第 6-10 章生成/修改代码**必须严格遵循**

### 1.3 术语
| 术语 | 解释 |
|------|------|
| DocNest | 基线通用 RAG 项目（`knowledge` 包） |
| EasyTour | 本项目 |
| retrieval_type | 内容类型（attraction/route/hotel/food/transport/culture/generic），**用于过滤召回** |
| answer_intent | 任务意图（lookup/recommendation/planning/comparison/howto/generic），**用于选择回答模板** |
| document_id | 一个上传文件对应的稳定主键（内容哈希派生） |
| chunk | 切片，Milvus 入库最小单位 |
| region_path | 形如 `海南/三亚/海棠湾` 的层级地区字符串 |

---

## 2. 项目背景与第一版范围

### 2.1 背景
时间紧任务重，基于 DocNest（通用 RAG）快速改造出旅游垂直知识库。

### 2.2 In Scope
1. 旅游内容导入（PDF / Markdown），自动抽取元数据
2. 导入/查询任务状态追踪
3. 景点检索与介绍（按目的地 + 景点名）
4. 线路检索（返回天数、预算）
5. 实用信息查询（酒店/美食/交通 + tips）
6. 知识问答 + 引用
7. 多轮对话、SSE 流式输出、历史管理

### 2.3 质量底线
- 单文件导入失败不影响整体服务
- 每个 answer 必须可追溯（citation 指向真实文档和主体）
- 查询链/导入链可独立演进

### 2.4 Out of Scope
用户账号、权限、多租户、订单、地图、跨语言、以图搜图、审核工作流。

---

## 3. 现有系统（DocNest）分析

### 3.1 技术栈
FastAPI + LangGraph + Milvus（dense+sparse）+ MinIO + MongoDB + DashScope（embedding/LLM/rerank）+ MinerU（PDF→MD）+ 静态 HTML 前端。

### 3.2 管线
**导入链（7 节点）**
```
entry → [pdf_to_md | md 直连] → md_img → document_split
→ item_name_recognition → bge_embedding_chunks → import_milvus
```

**查询链（7 节点）**
```
item_name_confirm → [vector_search ‖ hyde_search ‖ mcp_search]
→ rrf → rerank → answer_output
```

### 3.3 现有 Milvus chunks schema
| 字段 | 类型 |
|------|------|
| chunk_id | INT64 主键自增 |
| dense_vector | FLOAT_VECTOR(1024) |
| sparse_vector | SPARSE_FLOAT_VECTOR |
| content | VARCHAR(65535) |
| title / parent_title / file_title | VARCHAR(65535) |
| item_name | VARCHAR(65535) |
| enable_dynamic_field | True |

### 3.4 现有 API
`POST /upload` / `POST /query` / `GET /stream/{task_id}` / `GET /status/{task_id}` / `GET /history/{session_id}` / `DELETE /history/{session_id}` / `GET /healthz`

### 3.5 DocNest 对 EasyTour 不友好的点
1. item_name 单值，不适应"一篇文档多实体"
2. 缺旅游字段（content_type/region/document_id/时间元数据）
3. 单主体抽取无法覆盖多分类多实体
4. 查询链不区分内容类型和任务意图
5. 无文档去重能力

---

## 4. 需求差距分析

| 需求点 | DocNest 现状 | 差距 | 改造 |
|--------|-------------|------|------|
| 内容导入 | 单 item_name | 缺 content_type/region/多实体/document_id | 扩 state + 新 schema + 分层抽取 |
| 任务状态 | ✅ | 回写新字段 | 加 region/content_type/doc_main_entities |
| 景点检索 | 通用向量 | 缺过滤 + 结构化输出 | 加 retrieval_type filter + 结构化 prompt |
| 线路检索 | 通用向量 | 缺 days/budget | chunk 级少量字段抽取 + 结构化 prompt |
| 实用信息 | 通用向量 | 缺 tips/注意事项 | 答案模板分类（按 answer_intent） |
| 知识问答 | ✅ | 引用格式优化 | citation 增加 display_label |
| 多轮/流式 | ✅ | - | 直接复用 |

---

## 5. 第一版目标架构设计

### 5.1 整体架构
```
┌──────────────────── 前端（静态 HTML） ────────────────────┐
│  chat.html             import.html（文件+可选元数据）     │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│ FastAPI 接入层                                            │
│ /upload /query /stream /status /history /meta/*          │
└────┬───────────────┬──────────────────┬─────────────────┘
     ▼               ▼                  ▼
┌──────────┐ ┌──────────────┐ ┌──────────────┐
│ Import   │ │   Query      │ │   Meta       │
│ Service  │ │   Service    │ │   Service    │
└────┬─────┘ └──────┬───────┘ └──────────────┘
     ▼              ▼
┌─────────────┐ ┌─────────────────────────────────────────┐
│ 导入 Graph   │ │ 查询 Graph                                │
│              │ │ intent_route（retrieval_type+answer_intent)│
│ 文档级抽取    │ │ → alias_resolver → item_name_confirm     │
│ chunk 级抽取  │ │ → [vector ‖ hyde ‖ web] 并行              │
│              │ │ → rrf → rerank                          │
│              │ │ → structured_answer（按 answer_intent）  │
└──────┬───────┘ └──────────────┬──────────────────────────┘
       ▼                        ▼
┌──────────────────────────────────────────────────────────┐
│ Milvus（tour_chunks_v1 + tour_item_names_v1）            │
│ MinIO（原文件 + 图片 + source_uri_internal）               │
│ MongoDB（对话历史 + retrieval_trace + entity aliases）     │
│ DashScope（embedding / llm / rerank）                     │
└──────────────────────────────────────────────────────────┘
```

### 5.2 关键设计取舍（**全文唯一口径，下游章节必须引用**）

| 决策 | 方案 | 原因 |
|------|------|------|
| Milvus collection | **新建** `tour_chunks_v1` / `tour_item_names_v1` | 旧集合无旅游字段 |
| 上传元数据来源 | **双轨制**：file 必填；content_type/region/source_path **可选 override**；未传则走 LLM 抽取 | 默认零门槛，又给用户救火能力 |
| LLM 抽取分层 | **文档级抽全局字段一次** + **chunk 级只抽少量局部字段** | 成本/时延/一致性三杀缓解 |
| 过滤字段位置 | **热过滤字段必须显式 scalar schema**（见 6.2） | dynamic field 无索引会退化 brute-force |
| region 存储 | province / city / region_path 三字段 | 避免 `like "%三亚%"` 慢且歧义 |
| 主体字段 | chunk 级 primary_item_name + entity_names；文档级 doc_main_entities | 兼容多实体文档 |
| 意图建模 | retrieval_type（过滤）+ answer_intent（模板），两字段独立 | 推荐/规划类问题不应被内容类型绑架 |
| 文档去重 | **document_id = sha256(file_bytes)[:16]**（稳定，不含批次），ingest_batch_id 独立存另一字段 | 重传可识别；去重只看 document_id |
| Web 搜索 | **默认开启** ENABLE_WEB_SEARCH=true | 与需求"覆盖面优先"一致 |
| 回答模板 | 末尾按 answer_intent 选 prompt，不拆 graph | 保持召回链统一 |

### 5.3 目录结构

```
EasyTour/
├── easytour/                                  # 主代码包
│   ├── api/main.py                            # FastAPI 入口
│   ├── core/{deps,paths}.py                   # 依赖注入与路径
│   ├── schema/
│   │   ├── upload_schema.py                   # ✏️ 可选 override 字段
│   │   ├── query_schema.py                    # ✏️ 增加 structured/citations
│   │   ├── task_schema.py                     # ✏️ 增加旅游字段
│   │   └── meta_schema.py                     # ✅ 枚举 + 元数据模型
│   ├── services/
│   │   ├── import_file_service.py
│   │   ├── query_service.py
│   │   ├── task_service.py
│   │   ├── meta_service.py                    # ✅ 聚合 region/item
│   │   └── trace_service.py                   # ✅ 检索 trace 持久化
│   ├── processor/
│   │   ├── import_process/
│   │   │   ├── state.py                       # ✏️ 新字段
│   │   │   ├── config.py                      # ✏️ 新 collection
│   │   │   ├── main_graph.py                  # ✏️ 文档级抽取前置
│   │   │   └── nodes/
│   │   │       ├── entry_node.py
│   │   │       ├── file_hash_node.py          # ✅ 计算 file_hash/document_id
│   │   │       ├── pdf_to_md_node.py
│   │   │       ├── md_img_node.py
│   │   │       ├── document_split_node.py
│   │   │       ├── doc_level_extract_node.py  # ✅ 文档级抽取（全局字段）
│   │   │       ├── chunk_level_extract_node.py# ✅ chunk 级抽取（局部字段）
│   │   │       ├── bge_embedding_chunks_node.py
│   │   │       └── import_milvus_node.py      # ✏️ 新 schema
│   │   └── query_process/
│   │       ├── state.py                       # ✏️ 新字段
│   │       ├── config.py
│   │       ├── main_graph.py                  # ✏️ 加 intent_route
│   │       └── nodes/
│   │           ├── intent_route_node.py       # ✅ 双意图路由
│   │           ├── alias_resolver_node.py     # ✅ alias -> canonical 映射
│   │           ├── item_name_confirm_node.py
│   │           ├── vector_search_node.py      # ✏️ 加 filter
│   │           ├── hyde_search_node.py        # ✏️ 加 filter
│   │           ├── mcp_search_node.py
│   │           ├── rrf_node.py
│   │           ├── rerank_node.py
│   │           └── structured_answer_node.py  # ✏️ 按 answer_intent
│   ├── prompts/
│   │   ├── import_prompts.py                  # ✅ 文档级+chunk级抽取 prompt
│   │   └── query_prompts.py                   # ✏️ 按 answer_intent 分模板
│   ├── utils/                                 # providers/client/sse/history
│   └── front/{chat,import}.html
├── tests/
├── requirements.txt
├── .env.example
├── README.md
├── 需求说明.md
└── MVP改造技术方案.md                           # 本文档
```

---

## 6. 数据模型与元数据设计

### 6.1 枚举

**ContentType（内容类型，retrieval_type 取值）**
```python
class ContentType(str, Enum):
    ATTRACTION = "attraction"
    ROUTE = "route"
    HOTEL = "hotel"
    FOOD = "food"
    TRANSPORT = "transport"
    CULTURE = "culture"
    GENERIC = "generic"   # 兜底
```

**ItemType（主体类型）**：同 ContentType 前 6 项。

**AnswerIntent（任务意图，用于回答模板）**
```python
class AnswerIntent(str, Enum):
    LOOKUP = "lookup"               # 查信息（开放时间/门票）
    RECOMMENDATION = "recommendation" # 推荐（带孩子去哪）
    PLANNING = "planning"            # 规划（几日游）
    COMPARISON = "comparison"        # 对比（A 和 B 选哪个）
    HOWTO = "howto"                  # 怎么做（交通怎么坐）
    GENERIC = "generic"
```

### 6.2 Milvus `tour_chunks_v1` 字段表（**本节是 schema 唯一事实源**）

**热过滤字段（显式 scalar schema，必须建索引或允许 filter）**
| 字段 | 类型 | 说明 |
|------|------|------|
| chunk_id | INT64 主键自增 | |
| dense_vector | FLOAT_VECTOR(1024) | |
| sparse_vector | SPARSE_FLOAT_VECTOR | |
| content | VARCHAR(65535) | chunk 文本 |
| title | VARCHAR(512) | 段落标题 |
| parent_title | VARCHAR(512) | 父级标题 |
| file_title | VARCHAR(512) | 文件名 |
| **document_id** | VARCHAR(64) | 文档稳定主键（file_hash 派生） |
| **chunk_index** | INT64 | 文档内顺序 |
| **chunk_hash** | VARCHAR(64) | chunk 内容哈希（去重用） |
| **ingest_batch_id** | VARCHAR(64) | 本次导入批次 |
| **created_at** | INT64 | unix 毫秒 |
| **content_type** | VARCHAR(32) | 枚举值（ContentType） |
| **item_type** | VARCHAR(32) | 枚举值（ItemType） |
| **primary_item_name** | VARCHAR(256) | 当前 chunk 最主要主体，可为空 |
| **province** | VARCHAR(64) | 省份，如 "海南" |
| **city** | VARCHAR(64) | 城市，如 "三亚" |
| **region_path** | VARCHAR(256) | 如 "海南/三亚/海棠湾" |

**展示字段（dynamic field，不做过滤）**
- `entity_names: list[str]` — chunk 涉及的所有实体（含 7.6 标题兜底命中的）
- `suspected_new_entities: list[str]` — 标题兜底新发现的疑似主体（下期可能升级）
- `opening_hours: str`（attraction）
- `ticket_price: str`（attraction）
- `best_season: str`（attraction）
- `suitable_for: list[str]`（attraction / route，首版必抽，可为空）
- `attraction_features: list[str]`（attraction，首版必抽，可为空）
- `route_days: str`（route）
- `route_budget: str`（route）
- `price_range: str`（hotel / food）
- `hotel_tags: list[str]`（hotel）
- `food_tags: list[str]`（food）
- `tips: list[str]`（所有类型，首版必抽，可为空）
- `notes: list[str]`（所有类型，首版必抽，可为空）
- `image_urls: list[str]`

**启用 `enable_dynamic_field=True` 承载展示字段。**

### 6.3 Milvus `tour_item_names_v1` 字段表

| 字段 | 类型 | 说明 |
|------|------|------|
| item_id | INT64 主键自增 | |
| dense_vector / sparse_vector | 向量 | |
| item_name | VARCHAR(256) | **canonical 名** |
| item_type | VARCHAR(32) | |
| province / city / region_path | VARCHAR | |
| document_id | VARCHAR(64) | 来源文档 |

**aliases 不进 Milvus**，放 MongoDB `entity_aliases` 集合：
```
{ "item_name": "天涯海角", "aliases": ["天涯", "天涯海角景区"], "item_type": "attraction", "city": "三亚" }
```

### 6.4 MongoDB 集合设计

| 集合 | 用途 |
|------|------|
| `chat_message` | 与 DocNest 基线保持一致；存 session/role/text/timestamp + citations + retrieval_type + answer_intent + region |
| `entity_aliases` | 别名字典 |
| `retrieval_trace` | 见 6.7 |
| `documents` | 导入文档元数据索引（去重查询）+ `chunks_snapshot` / `rollback_snapshot`（供 metadata_only / reindex 提交回滚使用） |

**`documents` 集合关键字段（首版）**：
```json
{
  "document_id": "a1b2c3d4e5f6g7h8",
  "file_title": "三亚攻略.pdf",
  "document_title": "三亚海棠湾旅游攻略",
  "content_type": "attraction",
  "province": "海南",
  "city": "三亚",
  "region_path": "海南/三亚",
  "main_entities": [...],
  "chunk_count": 20,
  "last_ingest_batch_id": "...",
  "last_ingest_at": 1713345678000,
  "chunks_snapshot": [
    {
      "chunk_hash": "...",
      "chunk_index": 0,
      "dense_vector": [...],
      "sparse_vector": {...},
      "content": "...",
      "title": "...",
      "parent_title": "...",
      "file_title": "...",
      "primary_item_name": "...",
      "entity_names": ["..."]
    }
  ],
  "rollback_snapshot": null
}
```

### 6.5 ImportGraphState 扩展
```python
# 文件层
file_hash: str
document_id: str
ingest_batch_id: str
created_at: int
source_uri_internal: str       # 真实路径（内部）
source_label_display: str      # 前端展示用（文件名/来源标签）

# 用户 override（上传接口可选传入）
override_content_type: str
override_region: str            # 输入后自动解析到 province/city/region_path
override_source_path: str       # 网页 URL 时填这里

# 文档级抽取结果（文档级 LLM 一次抽取）
doc_content_type: str
doc_province: str
doc_city: str
doc_region_path: str
doc_main_entities: list[dict]   # [{item_name, item_type, aliases}]
document_title: str

# chunk 级结果
chunks: list[dict]              # 每个 chunk 的字段见 6.2 展示字段表
                                # 必带：content, chunk_hash, chunk_index, primary_item_name,
                                #       entity_names, suspected_new_entities, tips, notes
                                # 按 content_type 条件带：opening_hours / ticket_price /
                                #       best_season / suitable_for / attraction_features /
                                #       route_days / route_budget / price_range / hotel_tags /
                                #       food_tags / image_urls
suspected_new_entities: list[str]  # 汇总本次导入所有 chunk 的疑似新主体（供后续观察）
```

### 6.6 QueryGraphState 扩展
```python
retrieval_type: str             # ContentType
answer_intent: str              # AnswerIntent
region_filter: dict             # {province, city, region_path}
resolved_aliases: list[dict]    # [{alias, canonical_name}]
confirmed_item_name: str        # 主体高置信命中（进 filter）
candidate_item_names: list[str] # 主体中置信候选（进 rerank 前加权）
retrieval_filters: str          # 传给 Milvus 的 expr（用于调试落库）
structured_answer: dict
citations: list[dict]           # [{file_title, item_name, city, source_label_display, document_id}]
topk_chunk_ids: list[int]
topk_scores: list[float]
reranked_chunk_ids: list[int]
latency_ms: dict                # {intent_route, vector, hyde, mcp, rrf, rerank, answer}
```

### 6.7 检索 trace（MongoDB `retrieval_trace`）
```json
{
  "task_id": "...",
  "session_id": "...",
  "original_query": "...",
  "rewritten_query": "...",
  "retrieval_type": "attraction",
  "answer_intent": "recommendation",
  "region_filter": {"province": "海南", "city": "三亚"},
  "milvus_expr": "content_type == \"attraction\" and city == \"三亚\"",
  "topk_chunk_ids": [...],
  "topk_scores": [...],
  "reranked_chunk_ids": [...],
  "model_name": "qwen-plus",
  "latency_ms": {...},
  "created_at": 1713345678000
}
```
**不回前端**，仅用于后端调试。前端只看 answer/structured/citations。

### 6.8 source_path 安全处理
- `source_uri_internal`：本地路径 / 内部 URI，**禁止前端展示**
- `source_label_display`：展示用字符串（优先取 document_title，否则 file_title）
- citation 对外只返回 `source_label_display` + `document_id`

### 6.9 region 规整
- 所有 LLM 抽取或用户 override 的 region，统一走 `normalize_region(text) -> (province, city, region_path)`
- 未知地区 → province/city 留空，region_path=原文
- 过滤规则：
  - 优先 `city == "X"` 精确匹配
  - 否则 `region_path like "海南/三亚%"` 前缀匹配
  - **禁止** `region like "%三亚%"`

---

## 7. 导入链设计

### 7.1 节点清单

| 节点 | 来源 | 改造 | 职责 |
|------|------|------|------|
| entry_node | 复用 | - | 文件后缀分支 |
| **file_hash_node** | ✅ 新 | - | 计算 file_hash/document_id，查 documents 判重 |
| pdf_to_md_node | 复用 | - | MinerU |
| md_img_node | 复用 | - | 图片提取 |
| document_split_node | 复用 | 微调 | 按标题层次切分 |
| **doc_level_extract_node** | ✅ 新 | - | 文档级一次性 LLM 抽取（全局字段） |
| **chunk_level_extract_node** | ✅ 新 | - | chunk 级 LLM 抽取（少量局部字段） |
| bge_embedding_chunks_node | 复用 | - | 向量化 |
| import_milvus_node | 复用 | ✏️ | 新 collection + 新 schema |

### 7.2 文档级抽取（doc_level_extract_node）

**输入**：`md_content` 前 N 字（默认 4000） + 文件名 + 用户 override 字段
**单次 LLM 调用**，JSON Schema 输出：
```json
{
  "content_type": "attraction",
  "province": "海南",
  "city": "三亚",
  "region_path": "海南/三亚",
  "document_title": "三亚海棠湾旅游攻略",
  "main_entities": [
    {"item_name": "天涯海角", "item_type": "attraction", "aliases": ["天涯"]},
    {"item_name": "亚龙湾", "item_type": "attraction", "aliases": []}
  ]
}
```

**override 规则**：用户 override_* 字段优先覆盖 LLM 输出。

**兜底**：
- content_type 失败 → "generic"
- 地区失败 → 用文件名 + 全文做关键词正则（中国省/市词表）
- main_entities 失败 → 空列表

### 7.3 chunk 级抽取（chunk_level_extract_node）

**为了对齐需求文档（景点特色 / 适合人群 / 最佳季节 / tips / 注意事项），首版必须抽出对应字段。**
但为了控制成本和时延，**按 doc_content_type 分类只抽该类必须的字段**，其他字段允许为空不强抽。

**共有字段（所有类型都抽）**：
1. `primary_item_name`：当前 chunk 最主要主体（从 doc_main_entities 中选，或 null）
2. `tips: list[str]`：实用 tips（没有 → 空列表）
3. `notes: list[str]`：注意事项（没有 → 空列表）

**按 doc_content_type 分类的专有字段**：
| content_type | 专有字段 |
|-------------|---------|
| attraction | `opening_hours` / `ticket_price` / `best_season` / `suitable_for`（list[str]）/ `attraction_features`（list[str]） |
| route | `route_days` / `route_budget` / `suitable_for` |
| hotel | `price_range` / `hotel_tags`（list[str]） |
| food | `price_range` / `food_tags`（list[str]） |
| transport | （仅 tips/notes，无专有） |
| culture | （仅 tips/notes，无专有） |

**质量约定**（写入 prompt 模板）：
- 字段一律 **"原文明确支持才抽，不得脑补"**；不明 → 留空/空列表
- 所有字段允许为空，**不作为导入阻断条件**
- LLM 调用失败 → 该 chunk 所有专有字段置空，不抛异常

**`entity_names` 生成（不调 LLM，见 7.6）。**

**批量调用**：chunks 按 batch（默认 5）并发抽取；整个文档最多并发 2 个 batch。预估时延：平均 20 个 chunk 的文档 ≈ 15 秒内完成 chunk 级抽取。

### 7.6 entity_names 生成规则（**新增**，不调 LLM）

**输入**：chunk 文本 + doc_main_entities + chunk 自身 title/parent_title

**步骤**：
1. **doc_main_entities 匹配**：逐个用 canonical 名 + aliases 在 chunk 内做字符串匹配，命中即加入
2. **标题启发式兜底**（防止文档级漏抽）：
   - 扫描 chunk 的 `title` 和 `parent_title`
   - 若标题去掉前后空白后长度在 2-20 字之间、且包含"景区/寺/湾/岛/塔/山/海/酒店/街/馆"等旅游领域后缀关键词
   - 且**未出现在 doc_main_entities 的 canonical 或 aliases** 中
   - 则视为"疑似临时主体"加入 entity_names，并同时记录到 state 的 `suspected_new_entities` 字段供观察
3. 去重返回

**为什么不直接写回 doc_main_entities**：保守起见，疑似主体不进入 `tour_item_names_v1` 集合（不参与主体确认召回），仅停留在 chunk 的 entity_names 里，下期可根据 `suspected_new_entities` 统计结果决定是否升级为正式主体。

### 7.4 import_milvus_node 改造

- collection 名 `tour_chunks_v1`
- schema 严格按 6.2 表（热过滤字段显式定义 + 索引）
- 展示字段通过 `enable_dynamic_field=True` + chunk dict 额外 key 自动写入
- `REBUILD_MILVUS_COLLECTION=true` 时 drop 重建（开发方便）

### 7.5 文档去重策略（首版简化，**与 5.2 口径一致**）

**字段定义（唯一事实源）**：
- `file_hash` = `sha256(file_bytes)`（64 位十六进制）
- `document_id` = `file_hash[:16]`（稳定内容标识，**不含任何批次/时间信息**）
- `ingest_batch_id` = `uuid4().hex`（每次上传独立生成，用于追踪本次导入任务，与 document_id 正交）
- `chunk_hash` = `sha256(chunk.content)[:16]`

**去重规则**：
- 上传时先查 MongoDB `documents.document_id`：
  - **命中 + 无 force**：返回 `{"message": "Document already imported", "document_id": "...", "status": "already_imported"}`。**不返回 task_id**（原 task_id 是进程内存态，重启后查不到）。前端应据 `document_id` 调 `/documents/{id}` 查持久化的导入结果。
  - **命中 + force=metadata_only**：只允许修正**不影响 chunk 结构**的文档级元数据（如 `region` / `source_path` / `document_title` / `source_label_display`）。若检测到 `content_type` 变化，接口直接返回 `409 requires_reindex`，**禁止**继续走 metadata_only。
  - **命中 + force=reindex**：先完整生成新版本 chunks 与向量快照，再执行**带回滚的 replace 提交**；旧版本在新版本提交成功前保持可查询。
  - **未命中**：正常入库。
- 同名不同内容 → file_hash 不同 → 视为新文档
- **ingest_batch_id 不参与判重**，仅作为"本次任务"的关联字段写入 chunks 和 retrieval_trace

### 7.5.1 force 参数详细约定

| force 取值 | 切分 | LLM 文档级抽取 | LLM chunk 级抽取 | embedding | Milvus | 用途 |
|-----------|------|---------------|-----------------|-----------|--------|------|
| 未传 | - | - | - | - | - | 判重短路 |
| `metadata_only` | 否 | 是 | 否 | 否 | 基于旧快照重写文档级标量字段 | 修正地区/来源/显示标题等**纯文档级元数据** |
| `reindex` | 是 | 是 | 是 | 是 | 离线生成 + replace-with-rollback 提交 | 文件内容相同但提取逻辑升级后重跑，或需要修正 `content_type` |

**metadata_only 实现要点**：
- 只允许修改 `region/province/city/region_path/source_path/source_label_display/document_title` 等**不影响 chunk 字段结构**的内容
- 后端先比较“当前 `documents.content_type`”与“override / doc_level_extract 结果”：
  - 相同 → 允许 metadata_only
  - 不同 → 直接返回 `409 requires_reindex`
- Milvus 不支持原地 update，改为 `delete(expr="document_id == X")` + `insert(旧 chunks_snapshot 中的原向量与内容 + 新文档级标量字段)`
- `documents.chunks_snapshot` 是 metadata_only 的唯一事实源；若快照缺失，则拒绝 metadata_only，要求走 reindex

**reindex 安全提交要点（replace-with-rollback）**：
1. 先在任务工作目录 / `documents.pending_chunks_snapshot` 中跑完整导入链，生成**新版本完整快照**；此阶段**不改动**线上可查询 chunks
2. 提交前，把当前线上版本复制到 `documents.rollback_snapshot`
3. 进入提交阶段：
   - `delete(expr="document_id == X")`
   - `insert(新版本 chunks_snapshot)`
4. 若 `insert` 失败：
   - 立即用 `rollback_snapshot` 恢复旧版本 chunks
   - `documents.last_ingest_batch_id` / 元数据保持旧值
   - 任务标记 FAILED
5. 只有当新版本插入成功后，才更新 `documents.last_ingest_batch_id`、`chunk_count`、元数据并清空 `rollback_snapshot`

**关键原则**：`reindex` 是**先离线重建，再提交替换**，不是“先删旧数据再慢慢跑全链”。

---

## 8. 查询链设计

### 8.1 节点清单

| 节点 | 来源 | 改造 | 职责 |
|------|------|------|------|
| **intent_route_node** | ✅ 新 | - | 一次 LLM 调用，同时输出 retrieval_type + answer_intent + region_filter |
| **alias_resolver_node** | ✅ 新 | - | 用 Mongo `entity_aliases` + LRU cache 把 alias 归一到 canonical name |
| item_name_confirm_node | 复用 | 微调 | 接新 item_names 集合 |
| vector_search_node | 复用 | ✏️ | 加 filter 表达式 |
| hyde_search_node | 复用 | ✏️ | 加 filter + HyDE prompt 领域化 |
| mcp_search_node | 复用 | - | 默认开启 |
| rrf_node | 复用 | - | |
| rerank_node | 复用 | - | |
| **structured_answer_node** | 改造 | ✏️ | 按 **answer_intent** 选 prompt；落 trace |

### 8.2 intent_route_node

**输入**：original_query + history 最近 2 轮
**输出**：
```json
{
  "retrieval_type": "attraction",
  "answer_intent": "recommendation",
  "region_filter": {"province": "海南", "city": "三亚"},
  "rewritten_query": "..."
}
```

**fallback**：LLM 失败 → retrieval_type=generic, answer_intent=generic, region_filter 空（不过滤）。

### 8.2.1 alias_resolver_node

**执行位置**：`intent_route_node` 之后、`item_name_confirm_node` 之前。

**输入**：`original_query` / `rewritten_query` / `history` 最近 2 轮

**逻辑**：
1. 从 MongoDB `entity_aliases` 读取 alias 字典，命中结果放入本地 LRU cache
2. 扫描 query 中出现的 alias，映射到 canonical name
3. 若命中：
   - 在 `rewritten_query` 中注入 canonical name（保留原 alias 文本，避免语义丢失）
   - 在 state 写入 `resolved_aliases=[{alias, canonical_name}]`
   - 把 canonical name 作为 `item_name_confirm_node` 的优先入参
4. 若未命中：透传原 query，不阻塞主链

**例子**：
- 用户问：`天涯门票多少钱`
- alias_resolver 命中：`天涯 -> 天涯海角`
- 送入 item_name_confirm 的 rewritten_query 变为：`天涯（天涯海角）门票多少钱`

### 8.3 过滤表达式构造（含主体名"宽过滤"）

`item_name_confirm_node` 运行后会在 state 写入：
- `confirmed_item_name: str` — 高置信命中的主体名（阈值≥ `item_name_high_confidence`，默认 0.7）
- `candidate_item_names: list[str]` — 中置信命中的候选（用于加权，不进 filter）

**关键原则（v2.2 修订）**：**绝不使用 `primary_item_name == X` 作为唯一过滤条件**。旅游文档天然多实体（一条"三亚一日游"线路 chunk 的 primary 可能是"三亚一日游"而不是"天涯海角"），硬过滤会误杀线路/攻略类高价值 chunk。

**主体维度改为"宽过滤"：`primary_item_name == X` OR `entity_names 包含 X`**。

```python
def build_milvus_expr(retrieval_type: str, region: dict, confirmed_item_name: str,
                      supports_json_contains: bool = True) -> str | None:
    parts = []
    if retrieval_type and retrieval_type != "generic":
        parts.append(f'content_type == "{retrieval_type}"')

    if confirmed_item_name:
        safe = confirmed_item_name.replace('"', '\\"')
        if supports_json_contains:
            # Milvus 2.4+ 支持 JSON_CONTAINS(array_field, value)
            # entity_names 是 dynamic field 中的 list[str]
            parts.append(
                f'(primary_item_name == "{safe}" or '
                f'json_contains(entity_names, "{safe}"))'
            )
        else:
            # 兜底：只过 primary_item_name；entity_names 命中改由 8.4 加权补偿
            parts.append(f'primary_item_name == "{safe}"')

    if region.get("city"):
        parts.append(f'city == "{region["city"]}"')
    elif region.get("region_path"):
        parts.append(f'region_path like "{region["region_path"]}%"')
    elif region.get("province"):
        parts.append(f'province == "{region["province"]}"')
    return " and ".join(parts) if parts else None
```

**实现注意**：
- Milvus 2.4 起支持 `json_contains` 作用于 dynamic field 中的数组。启动时用一个小探针查询判断版本能力，把结果写入 `QueryConfig.milvus_supports_json_contains`
- 若不支持：`entity_names` 命中只在 8.4 加权中补偿，且把加权系数从 1.2 提升到 **1.5**（`entity_boost_factor_fallback`）
- 为了确保 `entity_names` 能被 json_contains 用到，导入端必须在写入 Milvus 时把它放到 dynamic KV 里（这一点 6.2 已经约定）

**禁止**出现 `like "%...%"` 中缀匹配。

### 8.4 rerank 前的实体名加权（中置信 + 不支持 json_contains 的兜底）

加权场景有两类：
1. **中置信候选**（`candidate_item_names`）：未达 filter 阈值，不写入 expr，通过加权提升排名
2. **json_contains 不可用兜底**：高置信 `confirmed_item_name` 只能通过 `primary_item_name` 过滤时，`entity_names` 命中的 chunk 在召回后通过更高加权系数补偿

```python
def boost_by_entity_hit(
    chunks: list[dict],
    candidates: list[str],
    confirmed: str | None,
    fallback_mode: bool,
    factor: float = 1.2,
    fallback_factor: float = 1.5,
) -> list[dict]:
    hit_targets = set(candidates or [])
    if confirmed and fallback_mode:
        hit_targets.add(confirmed)
    if not hit_targets:
        return chunks
    for ch in chunks:
        entities = set(ch.get("entity_names") or [])
        primary = ch.get("primary_item_name") or ""
        if primary:
            entities.add(primary)
        hit = entities & hit_targets
        if hit:
            use_factor = fallback_factor if (confirmed in hit and fallback_mode) else factor
            ch["_pre_rerank_score"] = ch.get("_pre_rerank_score", 1.0) * use_factor
    return sorted(chunks, key=lambda c: c.get("_pre_rerank_score", 1.0), reverse=True)
```

系数写入 `QueryConfig.entity_boost_factor`（默认 1.2）和 `entity_boost_factor_fallback`（默认 1.5）。

### 8.5 structured_answer_node

1. 按 **answer_intent** 选 prompt 模板（6 + 1 = 7 套）
2. Prompt 内明确"优先使用知识库上下文，Web 结果仅作补充"
3. 流式：answer 字段走 DELTA，structured / citations 在 FINAL_ANSWER 一次下发
4. citation 只取 source_label_display、item_name、city、document_id
5. 节点末尾调 trace_service 落库（含 topk_chunk_ids / scores / expr / latency）

### 8.6 Prompt 模板（按 answer_intent 分类）

| answer_intent | 输出结构示例 |
|---------------|------------|
| lookup | `{answer, facts: {opening_hours?, ticket_price?, ...}}` |
| recommendation | `{answer, recommendations: [{name, reason, best_season, city}]}` |
| planning | `{answer, itinerary: [{day, plan}], budget_hint}` |
| comparison | `{answer, comparison_table: [{aspect, a, b}]}` |
| howto | `{answer, steps: [...], tips?: [...]}` |
| generic | `{answer}` |

---

## 9. API 接口设计

### 9.1 接口一览

**`/healthz` 响应扩展**（帮助尽早发现 Mongo 静默降级）：
```json
{
  "status": "ok",
  "mongo_connected": true,
  "milvus_connected": true,
  "minio_connected": true
}
```
任一依赖不可用时 `status` 仍为 `ok`（服务可降级运行），但对应 `*_connected=false`，便于上线巡检。

| 方法 | 路径 | 来源 |
|------|------|------|
| POST | /upload | ✏️ 双轨制 + force |
| POST | /query | ✏️ 新响应字段 |
| GET | /stream/{task_id} | 复用 |
| GET | /status/{task_id} | ✏️ 新字段 |
| GET | /history/{session_id} | 复用 |
| DELETE | /history/{session_id} | 复用 |
| GET | /meta/regions | ✅ 新 |
| GET | /meta/items | ✅ 新 |
| GET | /meta/content_types | ✅ 新 |
| GET | /documents/{document_id} | ✅ 新（查导入结果） |
| GET | /healthz | 复用 |

### 9.2 POST /upload（multipart/form-data）
```
file: UploadFile                        # 必填
content_type: string (optional)          # attraction|route|hotel|food|transport|culture
region: string (optional)                # 自由文本，后端 normalize
source_path: string (optional)           # 网页/外部 URL
force: string (optional)                 # 空 | "metadata_only" | "reindex"
```

**响应（三种情况）**：

```jsonc
// 1) 新文件首次上传 / force=reindex / force=metadata_only：触发导入图
{
  "message": "File upload submitted",
  "status": "processing",
  "document_id": "a1b2c3d4e5f6g7h8",
  "task_id": "..."           // 进程内存态，仅本次服务活期内有效
}

// 2) 判重命中且未传 force：短路，不启动导入
{
  "message": "Document already imported",
  "status": "already_imported",
  "document_id": "a1b2c3d4e5f6g7h8"
  // 注意：无 task_id 字段。前端应调 GET /documents/{document_id}
}

// 3) 异常
{ "message": "...", "status": "error", "error": "..." }
```

### 9.2.1 GET /documents/{document_id}

返回持久化的文档元数据 + 最后一次导入结果，供判重短路后的前端展示。
```json
{
  "document_id": "...",
  "file_title": "...",
  "document_title": "...",
  "content_type": "attraction",
  "province": "海南", "city": "三亚", "region_path": "海南/三亚",
  "main_entities": [...],
  "chunk_count": 20,
  "last_ingest_batch_id": "...",
  "last_ingest_at": 1713345678000
}
```

### 9.3 POST /query
请求：
```json
{
  "query": "三亚有哪些必去景点？",
  "session_id": "...",
  "message_id": "...",
  "is_stream": true,
  "history": [...],
  "retrieval_type": "attraction",     // 可选 override
  "region": "三亚"                     // 可选 override
}
```
响应（非流式）：
```json
{
  "message": "Query completed",
  "session_id": "...",
  "task_id": "...",
  "rewritten_query": "...",
  "retrieval_type": "attraction",
  "answer_intent": "recommendation",
  "region": {"province": "海南", "city": "三亚"},
  "item_names": ["天涯海角", "亚龙湾"],
  "answer": "...",
  "structured": {...},
  "citations": [
    {"source_label_display": "三亚攻略", "item_name": "天涯海角",
     "city": "三亚", "document_id": "a1b2c3..."}
  ],
  "image_urls": [...],
  "error": ""
}
```

### 9.4 SSE 事件
READY / PROGRESS / DELTA / FINAL_ANSWER（含 structured & citations）/ FINAL / ERROR。

---

## 10. 模块改造清单（唯一事实源）

| 文件 | 操作 | 说明 |
|------|------|------|
| `easytour/` 整包 | ✅ | 从 `knowledge/` 拷贝改名 |
| `schema/upload_schema.py` | ✏️ | 新增 UploadOverride + `force` 枚举 + upload status |
| `schema/query_schema.py` | ✏️ | QueryRequest 加 retrieval_type/region；Response 加 structured/citations/answer_intent |
| `schema/task_schema.py` | ✏️ | 加 document_id/region/doc_main_entities |
| `schema/meta_schema.py` | ✅ | ContentType/ItemType/AnswerIntent/CitationModel |
| `api/main.py` | ✏️ | `/upload` 解析 `force`/override；返回 `already_imported` / `requires_reindex`；新增 `/meta/*`、`/documents/{id}`、增强版 `/healthz` |
| `services/import_file_service.py` | ✏️ | `file_hash` 判重 + `force` 分流；协调普通导入 / metadata_only / reindex |
| `services/query_service.py` | ✏️ | 组装 structured + citations + trace 落库 |
| `services/document_service.py` | ✅ | `documents` 集合读写、`chunks_snapshot`/`rollback_snapshot` 持久化、`metadata_only` 应用、reindex 提交/回滚、`/documents/{id}` 查询 |
| `services/meta_service.py` | ✅ | 聚合 city/province/item_name |
| `services/trace_service.py` | ✅ | 写 retrieval_trace |
| `utils/task_util.py` | ✏️ | 增加 `metadata_only_apply` / `reindex_commit` / `rollback_restore` 等状态标签 |
| `utils/region_normalizer.py` | ✅ | normalize_region 工具 |
| `utils/hashing.py` | ✅ | file_hash/chunk_hash |
| `processor/import_process/state.py` | ✏️ | 按 6.5 扩字段；补 `pending_chunks_snapshot` / `commit_mode` |
| `processor/import_process/config.py` | ✏️ | 新 collection；新 batch 参数 |
| `processor/import_process/main_graph.py` | ✏️ | 插入 file_hash / doc_level_extract / chunk_level_extract；**只负责离线构建，不负责线上 replace 提交** |
| `processor/import_process/nodes/file_hash_node.py` | ✅ | |
| `processor/import_process/nodes/doc_level_extract_node.py` | ✅ | |
| `processor/import_process/nodes/chunk_level_extract_node.py` | ✅ | 替代旧 item_name_recognition_node |
| `processor/import_process/nodes/import_milvus_node.py` | ✏️ | 新 schema；支持离线构建结果写入 `pending_chunks_snapshot` |
| `processor/query_process/state.py` | ✏️ | 按 6.6 扩字段 |
| `processor/query_process/config.py` | ✏️ | 新 collection；ENABLE_WEB_SEARCH=true |
| `processor/query_process/main_graph.py` | ✏️ | 插入 intent_route_node + alias_resolver_node |
| `processor/query_process/nodes/intent_route_node.py` | ✅ | 输出双意图 + region |
| `processor/query_process/nodes/alias_resolver_node.py` | ✅ | alias -> canonical，写 resolved_aliases |
| `processor/query_process/nodes/vector_search_node.py` | ✏️ | 用 build_milvus_expr（含主体维度）+ 记录 topk_scores |
| `processor/query_process/nodes/hyde_search_node.py` | ✏️ | 同上 + HyDE prompt 领域化 |
| `processor/query_process/nodes/rerank_node.py` | ✏️ | rerank 前先调 boost_by_entity_hit（中置信候选加权） |
| `processor/query_process/nodes/structured_answer_node.py` | ✏️ | 按 answer_intent 模板 + 落 trace |
| `prompts/import_prompts.py` | ✅ | 文档级 + chunk 级抽取 prompt（6 类） |
| `prompts/query_prompts.py` | ✏️ | 按 answer_intent 6+1 模板 |
| `front/import.html` | ✏️ | 单文件上传 + 可选 override/force 字段 + 判重短路后自动查 `/documents/{id}` 回显 + `requires_reindex` 提示 |
| `front/chat.html` | ✏️ | 展示 structured / citations；可选 region/retrieval_type 筛选 |
| `.env.example` | ✏️ | 新 collection + ENABLE_WEB_SEARCH=true + MONGO_* |
| `requirements.txt` | 📋 | 从 RAG 拷贝 |
| `tests/` | ✅ | 按第 12 章，覆盖 force/rollback/alias/`/documents`/`/healthz` |

---

## 11. 分阶段开发实施计划（2 天紧凑版）

### 阶段 0：脚手架搭建（0.5 天）
1. `knowledge/` → `easytour/` 拷贝，全局替换 import
2. requirements.txt / .env.example / README 同步
3. `uvicorn easytour.api.main:app` 起服务，/healthz 200
4. 用原 schema 跑通一次上传 + 查询（冒烟）

**验收**：服务起得来，冒烟通过。

### 阶段 1：数据模型 + 导入链骨架（0.5 天）
1. schema/meta_schema.py 三类枚举
2. utils/hashing.py + region_normalizer.py
3. ImportGraphState 按 6.5 扩展
4. import_milvus_node 切新 collection + 新 schema（允许 REBUILD=true 频繁 drop）
5. file_hash_node（输出稳定 document_id = file_hash[:16]，ingest_batch_id 独立生成）
6. doc_level_extract_node（全局字段 + main_entities）
7. chunk_level_extract_node（共有：primary_item_name + tips + notes；attraction 额外抽 suitable_for / attraction_features / opening_hours / ticket_price / best_season）
8. entity_names 生成器 + 标题启发式兜底（7.6 逻辑，不调 LLM）
9. `document_service` 落地：`documents` 集合结构、`chunks_snapshot` 持久化、`/documents/{id}` 查询
10. `/upload` 接 Form `override + force`，实现三条分支：
    - 无 force：判重 short-circuit
    - `metadata_only`：纯文档级元数据重写
    - `reindex`：进入离线重建
11. 实现 `requires_reindex` 判断：`metadata_only` 遇到 `content_type` 变化直接返回 409
12. 实现 reindex 的 replace-with-rollback 提交骨架：`pending_chunks_snapshot`、`rollback_snapshot`、`reindex_commit` / `rollback_restore`
13. `/healthz` 暴露 `mongo_connected` / `milvus_connected` / `minio_connected`

**验收**：
- 上传三亚 PDF，Milvus 查到 `content_type=attraction` / `city=三亚` / `document_id` 非空
- 同一 PDF 二次上传返回 `already_imported`，`/documents/{id}` 可回显持久化结果
- `metadata_only` 改地区成功；若改 `content_type` 则返回 `requires_reindex`

### 阶段 2：查询链改造（0.5 天）
1. QueryGraphState 按 6.6 扩展（含 confirmed_item_name / candidate_item_names）
2. intent_route_node（输出 retrieval_type + answer_intent + region_filter）
3. alias_resolver_node（Mongo `entity_aliases` + LRU，写 `resolved_aliases`）
4. item_name_confirm_node 输出 confirmed_item_name / candidate_item_names
5. vector_search / hyde_search 加 build_milvus_expr（含主体维度）
6. rerank 前插入 boost_by_entity_hit（8.4）
7. structured_answer_node 先实现 lookup + recommendation + generic 三套模板
8. trace_service 落 retrieval_trace（含 expr、confirmed_item_name、candidates、resolved_aliases）
9. /query 新响应字段

**验收**："三亚有哪些必去景点" → retrieval_type=attraction, answer_intent=recommendation, region={城=三亚}, structured.recommendations 非空。

### 阶段 3：多意图 Prompt + 前端 + Meta 接口（0.5 天）
1. 补齐 6 类 import 抽取 prompt + 6+1 类 query answer prompt
2. /meta/regions /meta/items /meta/content_types
3. chat.html 展示 structured / citations + 可选筛选器
4. import.html 增加 `force` 选项；判重 short-circuit 后自动调 `/documents/{id}`；`requires_reindex` 时给出明确提示

**验收**：需求第 4 章 4 个典型场景全跑通，前端可视化。

### 阶段 4：测试 + 调优（0.5 天）
1. 按第 12 章跑单元 + 集成测试
2. 重点补测高风险路径：`metadata_only`、`reindex` rollback、`alias_resolver_node`、`/documents/{id}`、增强版 `/healthz`
3. prompt 微调，README 补齐

---

## 12. 测试方案与验收标准

### 12.1 单元测试
| 模块 | 测试点 |
|------|-------|
| `region_normalizer` | "三亚" → 海南/三亚/海南/三亚；"海南省三亚市" 同上；"xxx" → 空 |
| `hashing` | 相同字节 → 相同 hash；不同字节 → 不同 |
| `doc_level_extract_node` | override 覆盖 LLM；LLM 失败时启发式兜底；main_entities 为空不抛 |
| `chunk_level_extract_node` | primary_item_name 能 null；按 content_type 选字段 schema 正确；tips/notes/suitable_for/attraction_features 字段存在即可（允许空列表） |
| `entity_names 生成` | doc_main_entities 命中；标题启发式兜底命中未登记主体；已登记主体不重复加入 suspected_new_entities |
| `alias_resolver_node` | alias 命中后写 `resolved_aliases`；未命中时不改 query；LRU 命中与 Mongo 回源都正确 |
| `build_milvus_expr` | 高置信主体进 filter；中置信不进 filter；各维度组合 expr 正确 |
| `boost_by_entity_hit` | 命中候选主体的 chunk 排序靠前；无候选时原序返回 |
| `import_milvus_node` | 新字段写入；dynamic 字段写入；REBUILD 正常 drop |
| `document_service.metadata_only` | 仅允许文档级字段改写；`content_type` 变化时返回 `requires_reindex`；快照缺失时拒绝执行 |
| `document_service.reindex_commit` | 新版本提交成功后更新 `last_ingest_batch_id`；提交失败时触发 rollback 恢复旧版本 |
| `/documents/{document_id}` | 命中文档时返回持久化元数据与 `chunk_count`；未命中返回 404 |
| `/healthz` | 依赖可用性布尔字段正确；某依赖断开时 `status=ok` 但对应 `*_connected=false` |
| `intent_route_node` | 6 类典型 query 识别准确；推荐/规划类拿到正确 answer_intent |
| `build_milvus_expr` | 各种组合生成正确 expr；无地区/无类型时返回 None |
| `structured_answer_node` | 按 answer_intent 选对模板；citation 只包含 display 字段 |
| `trace_service` | 写入字段完整；不阻塞主链 |

### 12.2 集成测试
| 场景 | 输入 | 期望 |
|------|------|------|
| 4.1 景点推荐 | "三亚有哪些必去景点" | answer_intent=recommendation, structured.recommendations 非空；recommendations 至少 1 项含 suitable_for 或 best_season |
| 4.2 景点详情 | "天涯海角开放时间" | answer_intent=lookup, confirmed_item_name="天涯海角"（高置信进 filter），structured.facts.opening_hours 非空 |
| 4.3 线路规划 | "云南 5 日游怎么安排" | answer_intent=planning, itinerary 天数=5 |
| 4.4 价格查询 | "三亚天涯海角门票多少" | answer_intent=lookup, structured.facts.ticket_price 非空 |
| 推荐类 | "带老人孩子适合去哪" | answer_intent=recommendation；至少 1 条返回主体命中 suitable_for 包含"老人"或"亲子"关键词 |
| 多轮追问 | 轮1 问景点，轮2 问"门票多少" | 保持三亚上下文，命中正确景点 |
| 重传 | 同一 PDF 上传两次 | 第二次返回 already_imported |
| `metadata_only` 纠错 | 同一 PDF，`force=metadata_only` + `region=海南省三亚市` | `/documents/{id}` 中地区字段更新；`chunk_count` 不变；无需重嵌入 |
| `metadata_only` 错分类保护 | 同一 PDF，`force=metadata_only` + `content_type=route` | 接口返回 `409 requires_reindex`，旧文档仍可查询 |
| `reindex` 回滚恢复 | 模拟 replace 提交时 insert 失败 | 旧版本 chunks 仍可查询；`documents.last_ingest_batch_id` 不变；任务状态 FAILED |
| alias 查询 | "天涯门票多少钱" | `resolved_aliases` 命中 `天涯 -> 天涯海角`；最终命中正确景点 |
| `/documents` 接口 | 上传后调用 `/documents/{document_id}` | 返回 document 元数据、`main_entities`、`chunk_count` |
| `/healthz` 增强 | 断开 Mongo 或 MinIO 后请求 `/healthz` | `status=ok`，但对应 `mongo_connected/minio_connected=false` |

### 12.3 质量标准
- Top-3 引用中至少 2 条命中正确地区/类型
- 非流式 < 10s；流式首字 < 3s
- 连续上传 10 个文档、问 20 次不崩
- 每个 answer 至少 1 条 citation
- 前端从不出现本地真实路径

### 12.4 测试数据
5-10 份旅游文档（覆盖三亚/云南/北京至少 3 地区，6 类 content_type 至少 4 类）。

---

## 13. 风险、限制与非目标

### 13.1 主要风险
| 风险 | 影响 | 缓解 |
|------|------|------|
| DashScope 限流 | 批量导入慢/失败 | batch 控并发；重试 |
| MinerU 超时 | PDF 卡住 | 保留 timeout；首版优先用 md |
| LLM 结构化输出不稳 | 字段缺 | response_format=json_object + 容错 parse |
| 文档级抽取分类错 | 整个文档走错 filter | 提供 override；前端展示抽取结果人工看得见 |
| chunk 级 primary_item_name 为空 | 部分答案缺实体锚定 | 允许 null；citation fallback 用 document_title |
| Web 搜索噪声 | 回答偏离知识库 | prompt 明确知识库优先；rerank 阈值卡严 |
| region 歧义 | 过滤错 | region_normalizer 统一；禁止 `%like%` |
| 标题启发式误判 | entity_names 混入非主体词 | 长度限制 + 领域后缀白名单；疑似主体单独存 suspected_new_entities 不污染主库 |
| 高置信主体过严 | confirmed_item_name 进 filter 后召回过窄 | 阈值 item_name_high_confidence 可通过 env 调；中置信走加权不走 filter |

### 13.2 已知限制
- 不支持跨语言
- 无 OCR 级图像检索
- 无真正的增量更新（只做 hash 判重，不支持版本管理）
- 无鉴权

### 13.3 非目标
见 2.4。

---

## 14. 部署与运行

### 14.1 依赖
Python 3.10+ / Milvus 2.4+ / MongoDB（必需：历史 + trace + aliases） / MinIO（可选） / DashScope / MinerU。

### 14.2 `.env.example` 关键项
```
# 新 collection
CHUNKS_COLLECTION=tour_chunks_v1
ITEM_NAME_COLLECTION=tour_item_names_v1
REBUILD_MILVUS_COLLECTION=false

# Web 搜索默认开启
ENABLE_WEB_SEARCH=true
MCP_DASHSCOPE_BASE_URL=...

# MongoDB（历史 + trace + aliases + documents 判重）
# 注意：与 DocNest 基线保持一致，env 名是 MONGO_DB_NAME（不是 MONGO_DB）
# 基线代码：knowledge/utils/mongo_history_util.py:49-52
MONGO_URL=mongodb://admin:123456@127.0.0.1:27017
MONGO_DB_NAME=easytour
```

### 14.3 启动
```bash
cd E:\SGG_AI\Practice_Code\EasyTour
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 14.4 端到端验证
1. 打开 `/import.html`，上传旅游 PDF（可选填 region / content_type override）
2. `/status/{task_id}` 轮询到 COMPLETED，页面显示抽取结果（province/city/content_type/doc_main_entities）
3. 打开 `/chat.html` 问"三亚有哪些必去景点"
4. 验证：retrieval_type / answer_intent / structured / citations 符合预期，citation 不含本地路径

---

## 附录 A：零改造复用清单
- `utils/providers/`（embedding/llm/rerank）
- `utils/client/storage_clients.py`
- `utils/sse_util.py`
- `utils/mongo_history_util.py`（扩展字段而非重写）
- `utils/task_util.py`
- `core/deps.py` / `core/paths.py`
- `processor/import_process/nodes/entry_node.py`
- `processor/import_process/nodes/pdf_to_md_node.py`
- `processor/import_process/nodes/md_img_node.py`
- `processor/import_process/nodes/bge_embedding_chunks_node.py`
- `processor/query_process/nodes/rrf_node.py`
- `processor/query_process/nodes/rerank_node.py`
- `processor/query_process/nodes/mcp_search_node.py`（**默认开启**，与 5.2 一致）

## 附录 B：Milvus filter 速查
```
# 精确
content_type == "attraction"
city == "三亚"
# 前缀
region_path like "海南/三亚%"
# 组合
content_type == "attraction" and city == "三亚"
# 禁止
region like "%三亚%"      ❌ 中缀匹配
content like "%门票%"     ❌ 对长文本慢
```

## 附录 C：region_normalizer 最小实现
- 内置省/市词表（中国 34 省 + 常见地级市 ≈ 300 条）
- 输入："三亚"、"海南三亚"、"三亚市"、"海南省三亚市海棠湾"
- 输出：`{province: "海南", city: "三亚", region_path: "海南/三亚[/xxx]"}`
- 无命中返回 `{province: "", city: "", region_path: 原文}`
