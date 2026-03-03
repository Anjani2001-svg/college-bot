import httpx
import os
from typing import Optional

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_AGENT_ID = os.getenv("BREVO_AGENT_ID", "")
BREVO_BASE_URL = "https://api.brevo.com/v3"

HEADERS = {
    "api-key": BREVO_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}


async def get_conversation_messages(conversation_id: str) -> list[dict]:
    """
    Fetch all messages for a given conversation from Brevo.
    Returns a list of message dicts ordered oldest-first.
    """
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

    # Convert Brevo message format to OpenAI-compatible history format
    history = []
    for msg in messages:
        msg_type = msg.get("type", "")
        text = msg.get("text", "") or msg.get("message", "")
        if not text:
            continue
        # "visitor" = user; anything else (agent, bot) = assistant
        role = "user" if msg_type in ("visitor", "contact") else "assistant"
        history.append({"role": role, "content": text})

    return history


async def send_message(conversation_id: str, text: str) -> dict:
    """
    Post a message into a Brevo conversation as the bot agent.
    """
    if not BREVO_API_KEY or not BREVO_AGENT_ID:
        raise ValueError(
            "BREVO_API_KEY and BREVO_AGENT_ID must be set in environment variables."
        )

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
    """
    Optionally reassign a conversation to a specific agent (or bot).
    """
    payload = {"agentId": agent_id or BREVO_AGENT_ID}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            f"{BREVO_BASE_URL}/conversations/{conversation_id}",
            headers=HEADERS,
            json=payload,
        )
        response.raise_for_status()
        return response.json()
