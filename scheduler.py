"""
scheduler.py
------------
Manages the 3-minute timer logic for auto-replies.

Flow:
  1. Visitor message arrives via webhook → schedule_bot_reply() is called.
  2. A job is added to fire in BOT_REPLY_DELAY_SECONDS (default 180).
  3. If a human agent replies before the timer fires → agent_has_replied() cancels the job.
  4. If the timer fires and no agent replied → bot generates and sends a reply.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# How many seconds to wait before the bot auto-replies (default = 3 minutes)
BOT_REPLY_DELAY_SECONDS = int(180)

# In-memory state: { conversation_id: {"pending": bool, "last_user_msg": str} }
_pending: dict[str, dict] = {}

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1},
)


def _job_id(conversation_id: str) -> str:
    return f"auto_reply_{conversation_id}"


async def _fire_bot_reply(conversation_id: str, user_message: str):
    """
    Called by APScheduler after the delay. Sends a bot reply if no agent
    has responded yet.
    """
    entry = _pending.get(conversation_id)
    if not entry or not entry.get("pending"):
        logger.info(
            "Conversation %s: agent already replied — skipping bot reply.",
            conversation_id,
        )
        return

    logger.info(
        "Conversation %s: no agent reply after %ds — bot is responding.",
        conversation_id,
        BOT_REPLY_DELAY_SECONDS,
    )

    # Lazy imports to avoid circular dependency at module load time
    from brevo_handler import get_conversation_messages, send_message
    from bot import get_reply

    try:
        history = await get_conversation_messages(conversation_id)
        # Remove last user message from history to avoid duplication
        # (we pass it explicitly to get_reply)
        if history and history[-1]["role"] == "user":
            history = history[:-1]

        reply_text = get_reply(user_message, history)
        await send_message(conversation_id, reply_text)
        logger.info("Conversation %s: bot reply sent.", conversation_id)

    except Exception as exc:
        logger.error(
            "Conversation %s: failed to send bot reply — %s", conversation_id, exc
        )
    finally:
        _pending[conversation_id]["pending"] = False


def schedule_bot_reply(conversation_id: str, user_message: str):
    """
    Schedule an auto-reply job for this conversation.
    If a job already exists for this conversation, it is replaced
    (i.e. the timer resets if the visitor sends another message).
    """
    _pending[conversation_id] = {
        "pending": True,
        "last_user_msg": user_message,
        "received_at": datetime.utcnow(),
    }

    run_at = datetime.utcnow() + timedelta(seconds=BOT_REPLY_DELAY_SECONDS)

    scheduler.add_job(
        _fire_bot_reply,
        trigger="date",
        run_date=run_at,
        args=[conversation_id, user_message],
        id=_job_id(conversation_id),
        replace_existing=True,
    )
    logger.info(
        "Conversation %s: bot reply scheduled in %ds.",
        conversation_id,
        BOT_REPLY_DELAY_SECONDS,
    )


def agent_has_replied(conversation_id: str):
    """
    Call this when a human agent sends a message.
    Cancels the pending bot-reply job so the bot stays silent.
    """
    if conversation_id in _pending:
        _pending[conversation_id]["pending"] = False

    job_id = _job_id(conversation_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(
            "Conversation %s: agent replied — bot reply cancelled.", conversation_id
        )
