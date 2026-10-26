import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    ConversationRecord, MessageRecord, ProjectRecord, UserRecord, WorkspaceRecord,
    check_and_record_usage, ensure_user, get_db,
)

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(title="BIZORA AI API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class ProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class ConversationCreate(BaseModel):
    title: str = Field(default="Новый диалог", min_length=1, max_length=160)
    project_id: int | None = Field(default=None, gt=0)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Verify Telegram Mini App initData and return its parsed, trusted fields."""
    if not init_data or not bot_token:
        raise ValueError("Telegram initData and bot token are required")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
    except ValueError as exc:
        raise ValueError("Malformed Telegram initData") from exc

    if len(fields) != len(pairs):
        raise ValueError("Duplicate Telegram initData fields")

    received_hash = fields.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise ValueError("Missing or invalid Telegram hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram signature")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Missing or invalid Telegram user data") from exc

    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age_seconds:
        raise ValueError("Expired Telegram initData")
    if user_id <= 0:
        raise ValueError("Invalid Telegram user id")

    return {"user": user, "auth_date": auth_date}


def get_current_telegram_user(
    x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
) -> dict:
    """Reusable dependency for endpoints that require a verified Telegram user."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram authentication is not configured")
    try:
        verified = verify_telegram_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram initData") from exc

    user = verified["user"]
    try:
        owner_ids = {
            int(value.strip())
            for value in settings.owner_telegram_ids.split(",")
            if value.strip()
        }
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Owner configuration is invalid") from exc

    return {
        "id": int(user["id"]),
        "first_name": user.get("first_name", ""),
        "username": user.get("username"),
        "language_code": user.get("language_code"),
        "auth_date": verified["auth_date"],
        "role": "owner" if int(user["id"]) in owner_ids else "user",
    }


def require_owner(user: dict = Depends(get_current_telegram_user)) -> dict:
    """Reusable dependency that restricts an endpoint to configured owner IDs."""
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


def request_ai_reply(message: str, history: list[dict[str, str]] | None = None) -> str:
    """Call an OpenAI-compatible chat-completions endpoint without exposing provider errors."""
    try:
        response = httpx.post(
            settings.ai_provider_base_url,
            headers={
                "Authorization": f"Bearer {settings.ai_provider_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты BIZORA AI — практичный бизнес-ассистент. Отвечай на языке пользователя, "
                            "структурированно, конкретно и честно. Если данных не хватает, уточняй."
                        ),
                    },
                    *(history or [{"role": "user", "content": message}]),
                ],
                "temperature": 0.7,
                "max_tokens": 700,
            },
            timeout=30.0,
        )
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="AI provider is temporarily busy. Try again later.")
        response.raise_for_status()
        payload = response.json()
        reply = payload["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Empty AI response")
        return reply.strip()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="AI provider timed out. Please try again.") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI provider request failed. Please try again later.") from exc


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bizora-ai-api", "version": "0.4.0"}


@app.get("/api/config")
def public_config():
    return {
        "service": "BIZORA AI",
        "environment": settings.app_env,
        "ai_configured": bool(settings.ai_provider_api_key),
        "telegram_auth_configured": bool(settings.telegram_bot_token),
        "history_enabled": True,
    }


@app.post("/api/auth/telegram")
def telegram_auth(user: dict = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    ensure_user(db, user)
    db.commit()
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "first_name": user["first_name"],
            "username": user["username"],
            "language_code": user["language_code"],
        },
        "role": user["role"],
        "auth_date": user["auth_date"],
    }


@app.get("/api/me")
def current_user(user: dict = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    ensure_user(db, user)
    db.commit()
    return {"authenticated": True, "user": user}


@app.get("/api/owner")
def owner_dashboard(user: dict = Depends(require_owner)):
    return {"authorized": True, "role": "owner", "user_id": user["id"]}


def _workspace_for_user(db: Session, workspace_id: int, user_id: int) -> WorkspaceRecord:
    workspace = db.scalar(select(WorkspaceRecord).where(
        WorkspaceRecord.id == workspace_id,
        WorkspaceRecord.owner_telegram_id == user_id,
    ))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@app.get("/api/workspaces")
def list_workspaces(
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    ensure_user(db, user)
    rows = db.scalars(
        select(WorkspaceRecord)
        .where(WorkspaceRecord.owner_telegram_id == user["id"])
        .order_by(WorkspaceRecord.updated_at.desc(), WorkspaceRecord.id.desc())
    ).all()
    db.commit()
    return {"workspaces": [
        {"id": row.id, "name": row.name, "description": row.description,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
        for row in rows
    ]}


@app.post("/api/workspaces", status_code=201)
def create_workspace(
    request: WorkspaceCreate,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name cannot be empty")
    ensure_user(db, user)
    now = datetime.now(timezone.utc)
    row = WorkspaceRecord(
        owner_telegram_id=user["id"], name=name,
        description=request.description.strip(), created_at=now, updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"workspace": {
        "id": row.id, "name": row.name, "description": row.description,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }}


@app.get("/api/projects")
def list_projects(
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ProjectRecord)
        .where(ProjectRecord.owner_telegram_id == user["id"])
        .order_by(ProjectRecord.updated_at.desc(), ProjectRecord.id.desc())
    ).all()
    return {"projects": [
        {"id": row.id, "workspace_id": row.workspace_id, "title": row.title,
         "description": row.description, "status": row.status,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
        for row in rows
    ]}


@app.get("/api/workspaces/{workspace_id}/projects")
def list_workspace_projects(
    workspace_id: int,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    _workspace_for_user(db, workspace_id, user["id"])
    rows = db.scalars(
        select(ProjectRecord)
        .where(
            ProjectRecord.workspace_id == workspace_id,
            ProjectRecord.owner_telegram_id == user["id"],
        )
        .order_by(ProjectRecord.updated_at.desc(), ProjectRecord.id.desc())
    ).all()
    return {"projects": [
        {"id": row.id, "workspace_id": row.workspace_id, "title": row.title,
         "description": row.description, "status": row.status,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
        for row in rows
    ]}


@app.post("/api/workspaces/{workspace_id}/projects", status_code=201)
def create_project(
    workspace_id: int,
    request: ProjectCreate,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    _workspace_for_user(db, workspace_id, user["id"])
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Project title cannot be empty")
    now = datetime.now(timezone.utc)
    row = ProjectRecord(
        workspace_id=workspace_id, owner_telegram_id=user["id"], title=title,
        description=request.description.strip(), status="active",
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"project": {
        "id": row.id, "workspace_id": row.workspace_id, "title": row.title,
        "description": row.description, "status": row.status,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }}


@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, request: ProjectUpdate, user: dict = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    project = _project_for_user(db, project_id, user["id"])
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Project title cannot be empty")
    project.title = title
    project.description = request.description.strip()
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return {"project": {"id": project.id, "workspace_id": project.workspace_id, "title": project.title,
        "description": project.description, "status": project.status,
        "created_at": project.created_at.isoformat(), "updated_at": project.updated_at.isoformat()}}


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: int, user: dict = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    project = _project_for_user(db, project_id, user["id"])
    linked = db.scalar(select(ConversationRecord.id).where(ConversationRecord.project_id == project_id).limit(1))
    if linked is not None:
        raise HTTPException(status_code=409, detail="В проекте есть диалоги. Удалите их или перенесите перед удалением проекта.")
    db.delete(project)
    db.commit()
    return None


def _conversation_for_user(db: Session, conversation_id: int, user_id: int) -> ConversationRecord:
    conversation = db.scalar(select(ConversationRecord).where(
        ConversationRecord.id == conversation_id,
        ConversationRecord.telegram_id == user_id,
    ))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _project_for_user(db: Session, project_id: int, user_id: int) -> ProjectRecord:
    project = db.scalar(select(ProjectRecord).where(
        ProjectRecord.id == project_id,
        ProjectRecord.owner_telegram_id == user_id,
    ))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/projects/{project_id}/conversations")
def list_project_conversations(
    project_id: int,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
):
    _project_for_user(db, project_id, user["id"])
    rows = db.scalars(
        select(ConversationRecord)
        .where(ConversationRecord.project_id == project_id, ConversationRecord.telegram_id == user["id"])
        .order_by(ConversationRecord.updated_at.desc(), ConversationRecord.id.desc())
        .limit(limit)
    ).all()
    return {"conversations": [
        {"id": row.id, "project_id": row.project_id, "title": row.title,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
        for row in rows
    ]}


@app.post("/api/conversations", status_code=201)
def create_conversation(request: ConversationCreate, user: dict = Depends(get_current_telegram_user), db: Session = Depends(get_db)):
    title = request.title.strip() or "Новый диалог"
    ensure_user(db, user)
    if request.project_id is not None:
        _project_for_user(db, request.project_id, user["id"])
    now = datetime.now(timezone.utc)
    row = ConversationRecord(telegram_id=user["id"], title=title[:160], project_id=request.project_id, created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"conversation": {"id": row.id, "project_id": row.project_id, "title": row.title,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}}


@app.get("/api/conversations")
def list_conversations(
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    unassigned: bool = Query(default=False),
):
    ensure_user(db, user)
    query = select(ConversationRecord).where(ConversationRecord.telegram_id == user["id"])
    if unassigned:
        query = query.where(ConversationRecord.project_id.is_(None))
    rows = db.scalars(query
        .order_by(ConversationRecord.updated_at.desc(), ConversationRecord.id.desc())
        .limit(limit)).all()
    db.commit()
    return {"conversations": [
        {"id": row.id, "project_id": row.project_id, "title": row.title,
         "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()} for row in rows
    ]}


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    request: ConversationUpdate,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    conversation = _conversation_for_user(db, conversation_id, user["id"])
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title cannot be empty")
    conversation.title = title
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conversation)
    return {"conversation": {
        "id": conversation.id, "project_id": conversation.project_id, "title": conversation.title,
        "created_at": conversation.created_at.isoformat(), "updated_at": conversation.updated_at.isoformat(),
    }}


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    conversation = _conversation_for_user(db, conversation_id, user["id"])
    db.delete(conversation)
    db.commit()
    return None


@app.get("/api/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
):
    conversation = _conversation_for_user(db, conversation_id, user["id"])
    rows = db.scalars(select(MessageRecord)
        .where(MessageRecord.conversation_id == conversation.id)
        .order_by(MessageRecord.id.asc()).limit(limit)).all()
    return {"conversation_id": conversation.id, "messages": [
        {"id": row.id, "role": row.role, "content": row.content, "created_at": row.created_at.isoformat()}
        for row in rows
    ]}


@app.post("/api/chat/demo")
def demo_chat(
    request: DemoChatRequest,
    user: dict = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    ensure_user(db, user)
    if request.project_id is not None:
        _project_for_user(db, request.project_id, user["id"])
    if request.conversation_id is None:
        conversation = ConversationRecord(
            telegram_id=user["id"], title=message[:80] or "Новый диалог",
            project_id=request.project_id,
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _conversation_for_user(db, request.conversation_id, user["id"])
        if request.project_id is not None and conversation.project_id != request.project_id:
            raise HTTPException(status_code=404, detail="Conversation not found in this project")
    if conversation.title == "Новый диалог":
        conversation.title = message[:80]
    db.add(MessageRecord(conversation_id=conversation.id, role="user", content=message))
    db.flush()
    conversation.updated_at = datetime.now(timezone.utc)

    if not settings.ai_provider_api_key:
        reply = (
            "BIZORA AI принял задачу. Сейчас включён демонстрационный режим — "
            "AI-провайдер ещё не подключён, поэтому я не буду выдавать шаблонный текст "
            "за результат настоящей нейросети. Добавь ключ провайдера в переменные окружения "
            "backend, чтобы включить настоящие ответы AI."
        )
        db.add(MessageRecord(conversation_id=conversation.id, role="assistant", content=reply))
        db.commit()
        return {"mode": "demo", "reply": reply, "conversation_id": conversation.id, "project_id": conversation.project_id}

    limit = settings.owner_hourly_ai_limit if user["role"] == "owner" else settings.user_hourly_ai_limit
    try:
        check_and_record_usage(db, user, limit)
        db.commit()
        recent_rows = db.scalars(
            select(MessageRecord)
            .where(MessageRecord.conversation_id == conversation.id)
            .order_by(MessageRecord.id.desc())
            .limit(20)
        ).all()
        history = [
            {"role": row.role, "content": row.content}
            for row in reversed(recent_rows)
            if row.role in {"user", "assistant"}
        ]
        reply = request_ai_reply(message, history=history)
    except HTTPException:
        db.rollback()
        raise
    db.add(MessageRecord(conversation_id=conversation.id, role="assistant", content=reply))
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"mode": "ai", "reply": reply, "model": settings.ai_model, "conversation_id": conversation.id, "project_id": conversation.project_id}
