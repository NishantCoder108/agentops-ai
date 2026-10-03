from fastapi import APIRouter

from app.api.v1.endpoints import agent_runs, auth, chat, conversations, documents, health, users

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(chat.router)
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(agent_runs.router)
api_v1_router.include_router(documents.router)
