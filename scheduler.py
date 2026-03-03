import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# Read from .env — 10 for testing, 180 for live
BOT_REPLY_DELAY_SECONDS = int(os.getenv("BOT_REPLY_DELAY_SECONDS", "180"))

_pending: dict[str, dict] = {}

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1},
)

def _job_id(conversation_id: str) -> str:
    return f"auto_reply_{conversation_id}"

async def _fire_bot_reply(conversation_id: str, user_message: str):
    entry = _pending.get(conversation_id)
    if not entry or not entry.get("pending"):
        logger.info("Conversation %s: agent already replied - skipping.", conversation_id)
        return
    logger.info("Conversation %s: no agent reply after %ds - bot responding.", conversation_id, BOT_REPLY_DELAY_SECONDS)
    from brevo_handler import get_conversation_messages, send_message
    from bot import get_reply
    try:
        history = await get_conversation_messages(conversation_id)
        if history and history[-1]["role"] == "user":
            history = history[:-1]
        reply_text = get_reply(user_message, history)
        await send_message(conversation_id, reply_text)
        logger.info("Conversation %s: bot reply sent.", conversation_id)
    except Exception as exc:
        logger.error("Conversation %s: failed to send bot reply - %s", conversation_id, exc)
    finally:
        _pending[conversation_id]["pending"] = False

def schedule_bot_reply(conversation_id: str, user_message: str):
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
    logger.info("Conversation %s: bot reply scheduled in %ds.", conversation_id, BOT_REPLY_DELAY_SECONDS)

def agent_has_replied(conversation_id: str):
    if conversation_id in _pending:
        _pending[conversation_id]["pending"] = False
    job_id = _job_id(conversation_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Conversation %s: agent replied - bot reply cancelled.", conversation_id)
