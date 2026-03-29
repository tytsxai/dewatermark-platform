from __future__ import annotations


class AppError(Exception):
    def __init__(self, error_code: str, error_message: str, status_code: int = 400) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.status_code = status_code


def error_payload(error_code: str, error_message: str) -> dict[str, str]:
    return {
        "error_code": error_code,
        "error_message": error_message,
    }
