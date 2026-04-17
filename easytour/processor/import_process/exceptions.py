from __future__ import annotations

"""导入链异常定义。

这个文件和查询链异常文件的思路一样：
把导入流程里不同类型的错误统一分类，方便定位和理解。

对新手来说，最重要的是把它们当成“错误标签”：
- 看到 `PdfConversionError`，就知道问题出在 PDF 转 Markdown 这一步。
- 看到 `MilvusError`，就知道问题出在向量库。
- 看到 `StateFieldError`，就知道问题出在节点之间传递的 state 数据。
"""


def _build_message(field_name: str, expected_type: type | None = None) -> str:
    """为 state 字段错误生成统一文本。"""
    message = f"state['{field_name}'] is invalid"
    if expected_type is not None:
        message += f', expected {expected_type.__name__}'
    return message


class ImportProcessError(Exception):
    """导入流程的基础异常类型。"""

    def __init__(self, message: str, node_name: str = '', cause: Exception | None = None):
        self.node_name = node_name
        self.cause = cause
        super().__init__(message)

    def __str__(self) -> str:
        """把节点名和底层异常一起拼进最终错误文本。"""
        parts = []
        if self.node_name:
            parts.append(f'[{self.node_name}]')
        parts.append(super().__str__())
        if self.cause:
            parts.append(f'(cause: {self.cause})')
        return ' '.join(parts)


class StateFieldError(ImportProcessError):
    """state 字段缺失、为空、类型不对时抛出的错误。"""

    def __init__(
        self,
        node_name: str = '',
        field_name: str = '',
        expected_type: type | None = None,
        message: str = '',
        cause: Exception | None = None,
    ):
        super().__init__(message or _build_message(field_name, expected_type), node_name=node_name, cause=cause)


class ConfigurationError(ImportProcessError):
    """配置错误，例如环境变量缺失或配置不合法。"""


class FileProcessingError(ImportProcessError):
    """文件处理阶段错误的父类。"""


class PdfConversionError(FileProcessingError):
    """PDF 转 Markdown 阶段错误。"""


class ImageProcessingError(FileProcessingError):
    """Markdown 图片处理阶段错误。"""


class DocumentSplitError(ImportProcessError):
    """文档切分阶段错误。"""


class EmbeddingError(ImportProcessError):
    """向量化阶段错误。"""


class LLMError(ImportProcessError):
    """大模型调用阶段错误。"""


class StorageError(ImportProcessError):
    """存储层相关错误的父类。"""


class MilvusError(StorageError):
    """Milvus 相关错误。"""


class MinioError(StorageError):
    """MinIO 相关错误。"""


class ValidationError(ImportProcessError):
    """业务校验失败。"""
