import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

load_dotenv()

from scheduler import scheduler, schedule_bot_reply, agent_has_replied

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BREVO_API_KEY  = os.getenv("BREVO_API_KEY", "")
BREVO_AGENT_ID = os.getenv("BREVO_AGENT_ID", "")
BREVO_HEADERS  = {
    "api-key": BREVO_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}


async def fetch_message_text(message_id: str, chat_id: str = "") -> str:
    """
    Fetch the actual message text from Brevo.
    Tries multiple endpoints because Brevo Conversations API varies by plan.
    """
    endpoints = [
        # Single message by ID
        f"https://api.brevo.com/v3/conversations/messages/{message_id}",
    ]

    # Also try fetching messages list for the chat
    if chat_id:
        endpoints.append(
            f"https://api.brevo.com/v3/conversations/messages?conversationId={chat_id}&limit=5"
        )

    for url in endpoints:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, headers=BREVO_HEADERS)
                logger.info("Brevo fetch → %s [%s]", url, response.status_code)

                if response.status_code == 401:
                    logger.error("401 Unauthorized — check BREVO_API_KEY in your .env file!")
                    break  # No point retrying with same key

                if response.status_code == 200:
                    data = response.json()
                    logger.info("Brevo fetch response: %s", str(data)[:300])

                    # Single message dict
                    if isinstance(data, dict):
                        text = (data.get("text") or data.get("message") or data.get("content") or "").strip()
                        if text:
                            return text

                    # List of messages — find the visitor one
                    if isinstance(data, list):
                        for msg in reversed(data):
                            if msg.get("type") == "visitor":
                                text = (msg.get("text") or msg.get("message") or "").strip()
                                if text:
                                    return text

        except Exception as e:
            logger.error("Fetch failed for %s: %s", url, e)

    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting APScheduler...")
    scheduler.start()
    yield
    logger.info("Shutting down APScheduler...")
    scheduler.shutdown(wait=False)


app = FastAPI(title="South London College Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/test", response_class=HTMLResponse)
async def test_ui():
    html_path = Path(__file__).parent / "test_chat.html"
    if not html_path.exists():
        return HTMLResponse("<h2>test_chat.html not found</h2>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/webhook/brevo")
async def brevo_webhook(request: Request):
    data = await request.json()
    logger.info("BREVO RAW PAYLOAD: %s", data)

    event_name = (
        data.get("event_name")
        or data.get("eventName")
        or data.get("event")
        or ""
    ).lower()

    conversation_id = (
        data.get("conversationId")
        or data.get("conversation_id")
        or ""
    )

    # chat_id is inside identifiers — needed for fetching messages
    identifiers = data.get("identifiers") or {}
    chat_id = identifiers.get("chat_id") or ""

    logger.info("EVENT: %s | CONV ID: %s | CHAT ID: %s", event_name, conversation_id, chat_id)

    if not conversation_id:
        return {"status": "ignored", "reason": "no conversationId"}

    # ── message_received ──────────────────────────────────────────────────
    if event_name == "message_received":
        message_obj = data.get("message") or {}
        message_type = (message_obj.get("type") or "").lower()
        message_id   = message_obj.get("id") or ""

        logger.info("Message type: %s | ID: %s", message_type, message_id)

        if message_type == "visitor" and message_id:
            text = await fetch_message_text(message_id, chat_id)
            logger.info("Message text fetched: '%s'", text[:100] if text else "EMPTY")

            if text:
                schedule_bot_reply(conversation_id, text)
            else:
                logger.warning(
                    "Message text empty — BREVO_API_KEY may be wrong. "
                    "Check your .env file! Key starts with: %s",
                    BREVO_API_KEY[:12] + "..." if BREVO_API_KEY else "NOT SET"
                )

        elif message_type in ("agent", "operator"):
            agent_has_replied(conversation_id)

        return {"status": "ok", "event": "message_received"}

    # ── conversationFragment (fallback) ───────────────────────────────────
    if event_name == "conversationfragment":
        messages = data.get("messages") or []
        for msg in messages:
            mtype = (msg.get("type") or "").lower()
            text  = (msg.get("text") or "").strip()
            if mtype == "visitor" and text:
                schedule_bot_reply(conversation_id, text)
            elif mtype == "agent":
                agent_has_replied(conversation_id)
        return {"status": "ok", "event": "conversationFragment"}

    # ── conversationStarted ───────────────────────────────────────────────
    if event_name == "conversationstarted":
        message_obj  = data.get("message") or {}
        message_type = (message_obj.get("type") or "").lower()
        message_id   = message_obj.get("id") or ""
        if message_type == "visitor" and message_id:
            text = await fetch_message_text(message_id, chat_id)
            if text:
                schedule_bot_reply(conversation_id, text)
        return {"status": "ok", "event": "conversationStarted"}

    logger.warning("Unhandled Brevo event: '%s'", event_name)
    return {"status": "ignored", "event": event_name}


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    from bot import get_reply
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        reply = get_reply(payload.message, payload.history)
    except Exception as e:
        logger.error("Error generating reply: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(reply=reply)


@app.get("/health")
async def health():
    return {
        "status": "running",
        "scheduler": scheduler.running,
        "openai_key_set":  bool(os.getenv("OPENAI_API_KEY")),
        "brevo_key_set":   bool(BREVO_API_KEY),
        "brevo_agent_set": bool(BREVO_AGENT_ID),
        "brevo_key_preview": BREVO_API_KEY[:12] + "..." if BREVO_API_KEY else "NOT SET",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)