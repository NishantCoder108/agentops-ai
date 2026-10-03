# AgentOps AI

## Local Docker development

The stack runs four containers: the React frontend, the FastAPI backend, PostgreSQL with pgvector, and Redis.

PostgreSQL stores users, conversations, documents, and agent runs. Redis stores only the short-lived chat rate-limit counters. Passwords and the JWT signing key stay in a local `.env` file. `docker-compose.yml` references the variable names and does not contain those values.

### Start

```bash
cp .env.example .env
docker compose up --build
```

Edit `.env` before you share a machine or put a real model key in `OPENROUTER_API_KEY`. `JWT_SECRET` must be at least 32 characters. Chat can reach the model only when `OPENROUTER_API_KEY` is set; the rest of the stack still starts without it.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API health | http://localhost:8000/api/v1/health |
| API docs | http://localhost:8000/docs |

The frontend container serves the built app and proxies `/api` to the backend, so the browser stays on port 5173. On startup the backend applies database migrations, then serves the API.

### Stop

```bash
docker compose down
```

Postgres data remains in the `postgres-data` volume. Redis counters are dropped when that container stops. `docker compose down -v` deletes the database volume as well.
