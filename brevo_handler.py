import httpx
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

_api_key       = os.getenv("BREVO_API_KEY", "")
_conv_token    = os.getenv("BREVO_CONV_TOKEN", "")
BREVO_AGENT_ID = os.getenv("BREVO_AGENT_ID", "")
BREVO_BASE_URL = "https://api.brevo.com/v3"

# Use Conversations token if available (Pro plan), else fall back to main key
_active_key = _conv_token if _conv_token else _api_key

HEADERS = {
    "api-key": _active_key,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

async def get_conversation_messages(conversation_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{BREVO_BASE_URL}/conversations/messages",
            headers=HEADERS,
            params={"conversationId": conversation_id},
        )
        response.raise_for_status()
        data = response.json()
    messages = data.get("messages", data) if isinstance(data, dict) else data
    if not isinstance(messages, list):
        return []
    history = []
    for msg in messages:
        msg_type = msg.get("type", "")
        text = msg.get("text", "") or msg.get("message", "")
        if not text:
            continue
        role = "user" if msg_type in ("visitor", "contact") else "assistant"
        history.append({"role": role, "content": text})
    return history

async def send_message(conversation_id: str, text: str) -> dict:
    if not _active_key or not BREVO_AGENT_ID:
        raise ValueError("BREVO API key and BREVO_AGENT_ID must be set in .env")
    payload = {
        "conversationId": conversation_id,
        "text": text,
        "agentId": BREVO_AGENT_ID,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{BREVO_BASE_URL}/conversations/messages",
            headers=HEADERS,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

async def assign_agent(conversation_id: str, agent_id: Optional[str] = None) -> dict:
    payload = {"agentId": agent_id or BREVO_AGENT_ID}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{BREVO_BASE_URL}/conversations/{conversation_id}",
            headers=HEADERS,
            json=payload,
        )
        response.raise_for_status()
        return response.json()
