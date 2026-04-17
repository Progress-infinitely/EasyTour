from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


# 文本类型常量。
# embedding 接口会根据“这是文档”还是“这是查询”来选择更合适的编码方式。
TEXT_TYPE_DOCUMENT = 'document'
TEXT_TYPE_QUERY = 'query'
VALID_TEXT_TYPES = {TEXT_TYPE_DOCUMENT, TEXT_TYPE_QUERY}


class ProviderError(RuntimeError):
    """Provider 层的基础异常。

    只要是“模型提供方调用出了问题”，都可以先落到这一层。
    你可以把它理解成“模型能力封装层的总异常父类”。
    """


class ProviderConfigError(ProviderError):
    """Provider 配置错误。

    典型场景：
    - 缺少 API Key
    - 缺少 Base URL
    - 模型名没有配置
    """


class ProviderResponseError(ProviderError):
    """Provider 响应错误。

    典型场景：
    - 远端返回了异常结构
    - 返回结果为空
    - 返回字段类型不符合当前项目预期
    """


@dataclass(frozen=True)
class EmbeddingRecord:
    """一条 embedding 结果。

    这个数据类的作用是：
    把远程 embedding 接口的返回结果，
    规整成项目内部统一能识别的结构。

    字段说明：
    - `dense_vector`：稠密向量，适合表达整体语义
    - `sparse_vector`：稀疏向量，适合保留关键词信号
    - `provider_model`：实际使用的远端模型名
    - `dimension`：向量维度
    """

    dense_vector: list[float]
    sparse_vector: dict[int, float]
    provider_model: str
    dimension: int


@dataclass(frozen=True)
class RerankResult:
    """重排结果中的一条记录。

    这个数据类的作用是：
    把 rerank 模型返回的结果统一成：
    - 这条结果对应原始候选列表里的第几个
    - 这条文档文本是什么
    - 最终得分是多少
    """

    index: int
    document: str
    score: float


class LLMProvider(Protocol):
    """LLM Provider 协议。

    `Protocol` 可以先把它理解成“接口约定”。
    它不是具体实现，而是在说：

    “只要某个类实现了这些方法，我们就把它当成合法的 LLM Provider。”

    这样做的好处是：
    上层代码依赖的是“能力接口”，
    而不是死绑某一个具体类。
    """

    def get_client(
        self,
        *,
        model_name: str | None = None,
        temperature: float = 0.0,
        response_format: bool = False,
    ) -> Any:
        ...


class EmbeddingProvider(Protocol):
    """Embedding Provider 协议。

    它约定了：
    只要某个类能把文本列表转成 `EmbeddingRecord` 列表，
    我们就可以把它当成合法的 embedding provider。
    """

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        text_type: str,
        dimension: int = 1024,
    ) -> list[EmbeddingRecord]:
        ...


class RerankProvider(Protocol):
    """Rerank Provider 协议。

    它约定了两类能力：
    - `rerank(...)`：真正做重排
    - `estimate_tokens(...)`：估算请求成本
    """

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
        task_instruction: str,
    ) -> list[RerankResult]:
        ...

    def estimate_tokens(self, query: str, documents: Sequence[str]) -> int:
        ...
