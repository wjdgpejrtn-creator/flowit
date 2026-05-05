class DomainError(Exception):
    def __init__(self, message: str = "", *, code: str | None = None):
        self.code = code
        super().__init__(message)


class ValidationError(DomainError):
    pass


class AuthorizationError(DomainError):
    pass


class ExecutionError(DomainError):
    pass


class NotFoundError(DomainError):
    pass
