from app.core.exceptions import AppError


class AgentError(AppError):
    status_code = 500
    code = "agent_error"


class AgentMaxStepsExceededError(AgentError):
    status_code = 502
    code = "agent_max_steps_exceeded"
