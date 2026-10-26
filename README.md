# BIZORA AI

Futuristic AI business assistant delivered as a Telegram Mini App.

## MVP architecture

- `frontend/`: React + TypeScript + Vite Telegram Mini App UI.
- `backend/`: FastAPI service, health/config endpoints, Telegram WebApp init-data verification, quota-ready API boundary.
- `.github/workflows/ci.yml`: frontend build and backend tests on every push and pull request.

## Local development

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Set `VITE_API_BASE_URL` for the frontend if the API is not at `http://localhost:8000`.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Never commit bot tokens, API keys, or production secrets. Telegram authentication is verified server-side when `TELEGRAM_BOT_TOKEN` is configured. Without it, protected endpoints fail closed.

## Product roadmap

1. Foundation: Mini App shell, responsive UI, CI, health checks.
2. Core: Telegram identity verification, AI provider, chat history, quotas.
3. Workspace: projects, tasks, files, document tools.
4. Monetization: server-enforced plans, owner access, payment integration.
5. Expansion: CRM, research, scheduled automations.

The current chat endpoint is explicitly a safe demo placeholder until an AI provider and server-side secret are configured.