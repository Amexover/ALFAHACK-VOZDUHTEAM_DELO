import asyncio
import json
from contextlib import aclosing, suppress
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.assistant import knowledge, service
from app.assistant.config import settings
from app.assistant.context import audience_of, owned_conversation, resolve_scope
from app.assistant.gateway import QwenGateway
from app.assistant.models import Conversation, KnowledgeDocument, Turn
from app.assistant.schemas import ConversationIn, ConversationOut, DocumentIn, MessageIn, TurnOut
from app.core.db import get_db
from app.core.errors import ApiError, not_found
from app.core.security import current_user, staff_user
from app.enums import Role
from app.models import Company, User, utcnow
from app.staff_pipeline.security import member_of

router = APIRouter(prefix="/assistant", tags=["assistant"])
DocumentId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{0,79}$")]


def knowledge_editor(user: User = Depends(staff_user), db: Session = Depends(get_db)) -> User:
    member = member_of(db, user)
    if member.pipeline_enforced and not member.is_underwriter:
        raise ApiError(403, "FORBIDDEN", "Публиковать материалы может андеррайтер")
    return user


@router.get("/config")
def config(user: User = Depends(current_user)):
    audience = audience_of(user)
    intents = ["chat", "rating", "advice", "news"]
    if audience == "staff":
        intents += ["application_review", "draft_reply"]
    return {"enabled": settings.enabled, "model": settings.model, "audience": audience,
            "intents": intents, "max_message_characters": 6000, "streaming": True,
            "read_only": True, "news_mode": "curated", "data_mode": "synthetic",
            "suggestions": (["Что означает мой кредитный рейтинг?", "Как подготовить заявку?", "Какие есть материалы для бизнеса?"]
                            if audience == "client" else ["Подготовь сводку заявки", "Каких сведений не хватает?", "Составь черновик ответа клиенту"])}


@router.get("/health")
async def health(_: User = Depends(current_user)):
    return await QwenGateway().health()


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    scope = resolve_scope(db, user, body.company_id, body.application_id)
    db.execute(update(User).where(User.id == user.id).values(id=User.id))
    count = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.owner_id == user.id))
    if count >= 100:
        db.rollback()
        raise ApiError(429, "ASSISTANT_CONVERSATION_LIMIT", "Удалите ненужные диалоги перед созданием нового")
    conv = Conversation(id=str(uuid4()), owner_id=user.id, audience=scope.audience,
                        company_id=scope.company.id if scope.company else None,
                        application_id=scope.application.id if scope.application else None, title=body.title)
    db.add(conv)
    db.commit()
    return service.conversation_view(conv)


@router.get("/conversations")
def conversations(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  company_id: int | None = Query(None, gt=0), application_id: int | None = Query(None, gt=0),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    audience = audience_of(user)
    stmt = select(Conversation).outerjoin(Company, Conversation.company_id == Company.id).where(
        Conversation.owner_id == user.id, Conversation.audience == audience)
    if user.role == Role.CLIENT:
        stmt = stmt.where(or_(Conversation.company_id.is_(None), Company.owner_id == user.id))
    if company_id is not None:
        stmt = stmt.where(Conversation.company_id == company_id)
    if application_id is not None:
        stmt = stmt.where(Conversation.application_id == application_id)
    rows = db.scalars(stmt.order_by(Conversation.updated_at.desc(), Conversation.id).offset(offset).limit(limit + 1)).all()
    return {"items": [service.conversation_view(c) for c in rows[:limit]], "has_more": len(rows) > limit}


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def conversation(conversation_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv, _ = owned_conversation(db, user, str(conversation_id))
    return service.conversation_view(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    service.remove_conversation(db, user, str(conversation_id))
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: UUID, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_conversation(db, user, str(conversation_id))
    rows = db.scalars(select(Turn).where(Turn.conversation_id == str(conversation_id))
                      .order_by(Turn.created_at.desc(), Turn.id.desc()).offset(offset).limit(limit + 1)).all()
    return {"items": [service.turn_view(t) for t in reversed(rows[:limit])], "has_more": len(rows) > limit}


def replay_error(cached: dict):
    if cached["status"] == "failed":
        raise ApiError(409, cached["error_code"] or "ASSISTANT_FAILED",
                       "Предыдущая попытка не завершилась. Повторите сообщение с новым request_id")


@router.post("/conversations/{conversation_id}/messages", response_model=TurnOut)
async def message(conversation_id: UUID, body: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid, cid = user.id, str(conversation_id)
    turn_id, cached = service.reserve_turn(db, user, cid, body)
    db.close()
    if cached:
        replay_error(cached)
        return cached
    async with aclosing(service.generate(uid, cid, turn_id)) as events:
        async for event in events:
            if event["type"] == "done":
                return event["turn"]
            if event["type"] == "error":
                raise ApiError(event["status"], event["code"], event["message"])
    raise ApiError(500, "ASSISTANT_INTERNAL_ERROR", "Не удалось завершить сообщение")


@router.post("/conversations/{conversation_id}/messages/stream", response_class=StreamingResponse)
async def message_stream(conversation_id: UUID, body: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid, cid = user.id, str(conversation_id)
    turn_id, cached = service.reserve_turn(db, user, cid, body)
    db.close()
    if cached:
        replay_error(cached)

    def encode(event: dict) -> str:
        return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def stream():
        if cached:
            yield encode({"type": "done", "turn": cached, "replayed": True})
            return
        queue = asyncio.Queue(maxsize=16)

        async def produce():
            async with aclosing(service.generate(uid, cid, turn_id)) as events:
                async for event in events:
                    await queue.put(event)
            await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    break
                yield encode(event)
        finally:
            producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"})


@router.get("/knowledge")
def search_knowledge(q: str = Query(..., min_length=1, max_length=300), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": knowledge.search(db, audience_of(user), q)}


@router.get("/knowledge/{document_id}")
def knowledge_detail(document_id: DocumentId, user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {"client", "staff"} if audience_of(user) == "staff" else {"client"}
    doc = db.get(KnowledgeDocument, document_id)
    if doc and doc.audience in allowed:
        return knowledge.document_view(doc)
    builtin = next((d for d in knowledge.builtin_documents() if d["id"] == document_id and d["audience"] in allowed), None)
    if builtin:
        return builtin
    raise not_found("Материал не найден")


@router.put("/knowledge/{document_id}")
def put_document(document_id: DocumentId, body: DocumentIn, user: User = Depends(knowledge_editor), db: Session = Depends(get_db)):
    if document_id in {d["id"] for d in knowledge.builtin_documents()}:
        raise ApiError(409, "BUILTIN_DOCUMENT", "Встроенные правила формируются из конфигурации продукта")
    db.execute(update(User).where(User.id == user.id).values(id=User.id))
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        count = db.scalar(select(func.count()).select_from(KnowledgeDocument))
        if count >= 500:
            raise ApiError(409, "KNOWLEDGE_LIMIT", "Достигнут лимит базы знаний этой версии: 500 материалов")
        doc = KnowledgeDocument(id=document_id)
        db.add(doc)
    doc.title, doc.body, doc.audience, doc.kind = body.title, body.body, body.audience, body.kind
    doc.source_url = str(body.source_url) if body.source_url else None
    doc.published_at, doc.updated_at, doc.updated_by = body.published_at, utcnow(), user.id
    db.commit()
    return knowledge.document_view(doc)


@router.delete("/knowledge/{document_id}", status_code=204)
def delete_document(document_id: DocumentId, _: User = Depends(knowledge_editor), db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        raise not_found("Материал не найден")
    db.delete(doc)
    db.commit()
    return Response(status_code=204)


@router.get("/news")
def news(q: str = Query("", max_length=300), user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = knowledge.news(db, audience_of(user), q)
    return {"items": items, "has_real_news": any(not n["is_demo"] for n in items), "mode": "curated"}
