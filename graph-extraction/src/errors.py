from typing import List, Optional


class GraphExtractionError(Exception):
    """
    Base exception raised when graph extraction operations encounter errors.
    Supports wrapping original lower-level exceptions.
    """
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.original_error is not None:
            return f"{base_msg} (Caused by {type(self.original_error).__name__}: {self.original_error})"
        return base_msg


class LLMCommunicationError(GraphExtractionError):
    """
    Exception raised when LLM API request, authentication, timeout, rate limiting, or network fails.
    """
    pass


class MalformedLLMResponseError(GraphExtractionError):
    """
    Exception raised when LLM response cannot be parsed into valid structured graph output.
    """
    pass


class ExtractionValidationError(GraphExtractionError):
    """
    Exception raised when extracted graph data fails strict validation checks
    (e.g., dangling entity references, inconsistent triples, missing required fields).
    """
    def __init__(
        self,
        message: str,
        errors: Optional[List[str]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, original_error=original_error)
        self.errors = errors or []

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.errors:
            error_details = "\n  - " + "\n  - ".join(self.errors)
            return f"{base_msg}\nValidation Errors:{error_details}"
        return base_msg
