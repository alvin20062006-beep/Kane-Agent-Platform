# apps/api — FastAPI control plane

REST API for agents, tasks, conversations, skills, credentials, and local bridge integration. Data is persisted to a file-backed store by default (or PostgreSQL when configured).

## Run

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Verify

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/agents`
- `GET http://127.0.0.1:8000/docs` (OpenAPI)

Empty stores are seeded with the built-in agent (Kanaloa), two builtin skills, and a default execution policy — see `app/seed_data.py`.
