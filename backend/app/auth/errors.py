from app.core.exceptions import AppError


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Authentication is required") -> None:
        super().__init__(message)


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"

    def __init__(self) -> None:
        super().__init__("You do not have permission to do that")


class AuthNotConfiguredError(AppError):
    status_code = 500
    code = "auth_not_configured"

    def __init__(self) -> None:
        super().__init__(
            "Authentication is not configured",
            details={"missing_env_vars": ["JWT_SECRET"]},
        )


class EmailAlreadyRegisteredError(AppError):
    status_code = 409
    code = "email_taken"

    def __init__(self) -> None:
        super().__init__("Email is already registered")
