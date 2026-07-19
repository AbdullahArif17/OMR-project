from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data
        self.headers = headers
