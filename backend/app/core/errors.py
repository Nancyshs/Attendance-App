"""Domain errors, converted to clean JSON responses by the app-level handler."""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFound(ServiceError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class Conflict(ServiceError):
    def __init__(self, message: str, code: str = "conflict") -> None:
        super().__init__(message, status_code=409, code=code)


class Forbidden(ServiceError):
    def __init__(self, message: str = "Forbidden", code: str = "forbidden") -> None:
        super().__init__(message, status_code=403, code=code)
