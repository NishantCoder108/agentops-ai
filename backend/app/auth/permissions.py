from app.models.organization import UserRole


class Permission:
    MANAGE_DOCUMENTS = "manage_documents"
    VIEW_AGENT_RUNS = "view_agent_runs"
    MANAGE_USERS = "manage_users"
    CHAT = "chat"
    SEARCH_KNOWLEDGE = "search_knowledge"
    VIEW_OWN_CONVERSATIONS = "view_own_conversations"


_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.ADMIN: frozenset(
        {Permission.MANAGE_DOCUMENTS, Permission.VIEW_AGENT_RUNS, Permission.MANAGE_USERS}
    ),
    UserRole.USER: frozenset(
        {Permission.CHAT, Permission.SEARCH_KNOWLEDGE, Permission.VIEW_OWN_CONVERSATIONS}
    ),
}


def permissions_for(role: UserRole) -> frozenset[str]:
    return _ROLE_PERMISSIONS[role]
