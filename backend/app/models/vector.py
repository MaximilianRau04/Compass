"""Minimal SQLAlchemy type for Postgres pgvector columns (extension enabled in the first migration).

Using unsized `vector` lets the user switch between any embedding model (384, 768, 1024, 1536 dims)
without migrating the column.
"""

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "vector"

    def bind_processor(self, dialect):
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(f"{float(x):.7g}" for x in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value: str | list[float] | None) -> list[float] | None:
            if value is None or isinstance(value, list):
                return value
            text = value.strip()
            if text.startswith("[") and text.endswith("]"):
                inner = text[1:-1].strip()
                return [float(x) for x in inner.split(",")] if inner else []
            return None

        return process
