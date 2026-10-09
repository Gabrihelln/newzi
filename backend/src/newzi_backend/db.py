"""Database access for the API and the workers: SQLite (default) or PostgreSQL.

Application SQL is written once, in the subset both engines accept: ``?`` placeholders,
``INSERT ... ON CONFLICT`` upserts, explicit column lists, no PRAGMA/sqlite_master and no
date functions (timestamps are ISO-8601 text computed in Python). This module adapts what
remains different: placeholder style, row objects, numeric types, the write lock used by
job claims, and the database errors callers handle.

    DATABASE_URL=sqlite:///backend/data/product_backend.sqlite3   (default)
    DATABASE_URL=postgresql://user:password@host:5432/newzi         (requires psycopg)
"""
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

SQLITE = "sqlite"
POSTGRES = "postgres"


class DatabaseError(Exception):
    """Base for the portable error types below (raised in addition to the driver's own)."""


def _driver_errors(name):
    errors = [getattr(sqlite3, name)]
    try:
        import psycopg
        errors.append(getattr(psycopg, name))
    except ImportError:
        pass
    return tuple(errors)


# Catch these instead of sqlite3.* so handlers work on both engines.
IntegrityError = _driver_errors("IntegrityError")
OperationalError = _driver_errors("OperationalError")


def dialect_for(url):
    if url.startswith(("postgresql://", "postgres://")):
        return POSTGRES
    if url.startswith("sqlite:///") or "://" not in url:
        return SQLITE
    raise ValueError("DATABASE_URL must start with sqlite:/// or postgresql://")


def connect(url, sqlite_path=None):
    """Open a connection for ``url``; ``sqlite_path`` overrides the file for SQLite URLs."""
    if dialect_for(url) == POSTGRES:
        return PostgresConnection(url)
    return SQLiteConnection(sqlite_path or Path(url.removeprefix("sqlite:///")))


class _Connection:
    dialect = None

    def executemany(self, sql, rows):
        cursor = None
        for row in rows:
            cursor = self.execute(sql, row)
        return cursor

    def executescript(self, script):
        """Run ``;``-separated DDL (statements must not contain literal semicolons)."""
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def table_columns(self, table):
        raise NotImplementedError

    def string_agg(self, expression, separator=","):
        raise NotImplementedError


class SQLiteConnection(_Connection):
    dialect = SQLITE

    def __init__(self, path):
        self.raw = sqlite3.connect(path, timeout=30)
        self.raw.row_factory = sqlite3.Row
        for pragma in ("PRAGMA foreign_keys=ON", "PRAGMA busy_timeout=30000", "PRAGMA journal_mode=WAL"):
            self.raw.execute(pragma)

    def execute(self, sql, params=()):
        return self.raw.execute(sql, _params(params))

    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()

    @property
    def in_transaction(self): return self.raw.in_transaction

    def begin_immediate(self):
        """Start a transaction that holds the database write lock until commit/rollback."""
        self.raw.execute("BEGIN IMMEDIATE")

    def table_columns(self, table):
        return [row[1] for row in self.raw.execute(f"PRAGMA table_info({_identifier(table)})")]

    def string_agg(self, expression, separator=","):
        return f"GROUP_CONCAT({expression},'{separator}')"


class PostgresConnection(_Connection):
    dialect = POSTGRES
    # Arbitrary constant: one application-wide advisory lock emulates SQLite's database write lock.
    WRITE_LOCK_KEY = 4_810_391_772

    def __init__(self, url):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires: pip install 'psycopg[binary]>=3.2'") from exc
        self.raw = psycopg.connect(url, row_factory=_pg_row_factory, autocommit=False)
        _register_numeric_loader(self.raw)

    def execute(self, sql, params=()):
        # Always pass a sequence: psycopg only un-doubles %% when parameters are given.
        return self.raw.execute(_to_pyformat(sql), _params(params))

    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()

    @property
    def in_transaction(self):
        from psycopg.pq import TransactionStatus
        return self.raw.info.transaction_status != TransactionStatus.IDLE

    def begin_immediate(self):
        if self.in_transaction:
            self.raw.rollback()
        self.raw.execute("SELECT pg_advisory_xact_lock(%s)", (self.WRITE_LOCK_KEY,))

    def table_columns(self, table):
        return [row[0] for row in self.raw.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s "
            "ORDER BY ordinal_position", (table,))]

    def string_agg(self, expression, separator=","):
        return f"STRING_AGG(CAST({expression} AS TEXT),'{separator}')"


def _identifier(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"invalid identifier: {name}")
    return name


def _params(params):
    # SQLite stores booleans as 0/1 and the schema uses INTEGER flags; send the same to PostgreSQL.
    if isinstance(params, dict):
        return {k: int(v) if isinstance(v, bool) else v for k, v in params.items()}
    return tuple(int(v) if isinstance(v, bool) else v for v in params)


def _to_pyformat(sql):
    """``?`` -> ``%s`` outside string literals; literal ``%`` doubled for psycopg."""
    out = []; quote = None
    for char in sql:
        if quote:
            out.append("%%" if char == "%" else char)
            if char == quote: quote = None
        elif char in "'\"":
            quote = char; out.append(char)
        elif char == "?":
            out.append("%s")
        elif char == "%":
            out.append("%%")
        else:
            out.append(char)
    return "".join(out)


class Row(tuple):
    """sqlite3.Row-compatible row: index, slice or column-name access, ``keys()`` and ``dict(row)``."""
    __slots__ = ()
    _names = ()

    def __getitem__(self, key):
        if isinstance(key, str):
            try: return tuple.__getitem__(self, self._index[key])
            except KeyError: raise IndexError(f"No item with that key: {key}") from None
        return tuple.__getitem__(self, key)

    def keys(self): return list(self._names)


def _pg_row_factory(cursor):
    description = cursor.description
    if description is None:
        return tuple
    names = tuple(column.name for column in description)
    row_type = type("Row", (Row,), {"__slots__": (), "_names": names, "_index": {name: i for i, name in enumerate(names)}})
    return lambda values: row_type(values)


def _register_numeric_loader(connection):
    """SUM/AVG return NUMERIC in PostgreSQL; load it as int or float like SQLite, never Decimal."""
    from psycopg.types.numeric import NumericLoader

    class PlainNumberLoader(NumericLoader):
        def load(self, data):
            value = super().load(data)
            if isinstance(value, Decimal):
                return int(value) if value == value.to_integral_value() else float(value)
            return value
    connection.adapters.register_loader("numeric", PlainNumberLoader)
