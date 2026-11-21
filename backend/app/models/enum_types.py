"""Enum types whose label set is owned by Alembic revisions.

PostgreSQL enum labels can be added without touching the ORM, but SQLAlchemy
resolves *result* values against the labels declared on the column and raises
``LookupError`` for anything else (``sqlalchemy/sql/sqltypes.py``:
``Enum.result_processor`` calls ``_object_value_for_elem``). Declaring the new
labels in the models is not an option either: revision ``0001`` builds the
schema from the metadata, so revision ``0005``'s strict label validation would
then fail on a clean install.

``PermissiveEnum`` keeps the declared (historical) labels for DDL, binding and
comparison, and passes result values through unchanged so labels added by a
later revision stay readable.

The dialect adapts column types to its own implementations (the asyncpg
dialect maps ``sqltypes.Enum`` to ``AsyncPgEnum``), which would discard a plain
method override, so ``adapt`` re-applies the behaviour to the adapted class.
"""

from functools import lru_cache
from typing import Any

from sqlalchemy import Enum


@lru_cache(maxsize=None)
def _permissive_variant(base: type) -> type:
    """Permissive subclass of a dialect-specific Enum implementation."""

    return type(f"Permissive{base.__name__}", (PermissiveEnum, base), {})


class PermissiveEnum(Enum):
    """Native enum that does not validate database labels on read."""

    def _object_value_for_elem(self, elem: Any) -> Any:
        return elem

    def adapt(self, cls, **kw):
        if not (isinstance(cls, type) and issubclass(cls, Enum)):
            return super().adapt(cls, **kw)
        if issubclass(cls, PermissiveEnum):
            return super().adapt(cls, **kw)
        kw.setdefault("_enums", self._enums_argument)
        kw.setdefault("_disable_warnings", True)
        return super(Enum, self).adapt(_permissive_variant(cls), **kw)
