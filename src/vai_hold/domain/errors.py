from __future__ import annotations


class PersistenceError(Exception):
    pass


class DuplicateOrderError(PersistenceError):
    pass


class ConcurrencyError(PersistenceError):
    pass


class NotFoundError(PersistenceError):
    pass


class ConstraintError(PersistenceError):
    pass


class OracleNotImplemented(PersistenceError):
    pass


class UnknownPersistenceBackend(PersistenceError):
    pass


class SchemaError(PersistenceError):
    """SQLite file does not match canonical DDL. Recreate; do not ALTER in Python."""


class ConfigError(Exception):
    pass


class UnknownFunctionCode(Exception):
    pass


class ApplicationError(Exception):
    pass
