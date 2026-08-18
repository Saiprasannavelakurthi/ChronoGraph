class GraphExtractionError(Exception):
    """
    Exception raised when LLM invocation, API request, authentication, or network fails.
    Distinct from valid empty extraction or invalid LLM JSON output.
    """
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error
