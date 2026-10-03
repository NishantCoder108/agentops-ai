from app.core.exceptions import AppError


class AgentError(AppError):
    status_code = 500
    code = "agent_error"


class AgentMaxStepsExceededError(AgentError):
    status_code = 502
    code = "agent_max_steps_exceeded"


class AgentInvalidOutputError(AgentError):
    """The model cited a source the knowledge tool did not return, or its answer was not usable."""

    status_code = 502
    code = "agent_invalid_output"
