from __future__ import annotations


class PynamerError(Exception):
    pass


class ConfigurationError(PynamerError, ValueError):
    pass


class AnalysisError(PynamerError):
    pass


class TransformError(PynamerError):
    pass


class ValidationError(TransformError):

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source
