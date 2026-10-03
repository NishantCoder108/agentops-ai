from app.core.exceptions import AppError


class DatabaseNotConfiguredError(AppError):
    status_code = 500
    code = "database_not_configured"

    def __init__(self) -> None:
        super().__init__("Database is not configured", details={"missing_env_vars": ["DATABASE_URL"]})
