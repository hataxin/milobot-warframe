"""User-visible failures from external data and query validation."""


class QueryError(Exception):
    """A failed query with a concise explanation suitable for chat."""
