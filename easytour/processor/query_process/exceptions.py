from __future__ import annotations


class QueryProcessError(Exception):
    def __init__(self, message: str, node_name: str = '', cause: Exception | None = None):
        self.node_name = node_name
        self.cause = cause
        super().__init__(message)

    def __str__(self) -> str:
        parts = []
        if self.node_name:
            parts.append(f'[{self.node_name}]')
        parts.append(super().__str__())
        if self.cause:
            parts.append(f'(cause: {self.cause})')
        return ' '.join(parts)


class StateFieldError(QueryProcessError):
    def __init__(
        self,
        *,
        node_name: str = '',
        field_name: str = '',
        expected_type: type | None = None,
        message: str = '',
        cause: Exception | None = None,
    ):
        if not message:
            message = f"state['{field_name}'] is invalid"
            if expected_type is not None:
                message += f', expected {expected_type.__name__}'
        super().__init__(message, node_name=node_name, cause=cause)


class ValidationError(QueryProcessError):
    pass


class ConfigurationError(QueryProcessError):
    pass


class SearchError(QueryProcessError):
    pass


class EmbeddingError(QueryProcessError):
    pass


class LLMError(QueryProcessError):
    pass


class StorageError(QueryProcessError):
    pass


class MilvusError(StorageError):
    pass


class MongoDBError(StorageError):
    pass


class EntityAlignmentError(QueryProcessError):
    pass


class RerankError(QueryProcessError):
    pass


class ItemNameConfirmError(QueryProcessError):
    pass
