import os
import httpx
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from excel_loader import CourseLoader

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=httpx.Client(
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
    ),
    max_retries=2,
)

COURSES_PATH = Path(__file__).parent / "courses.xlsx"

try:
    loader = CourseLoader(str(COURSES_PATH))
    print(f"✅ Loaded {len(loader.df)} courses from {COURSES_PATH}")
except FileNotFoundError as e:
    print(f"❌ {e}")
    loader = None

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — SEARCH MODE (max 3 courses, brief)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Aria, a warm and friendly admissions assistant for South London College.
Your job is to help learners find the right course and feel excited about studying.

South London College offers courses in IT, computing, cyber security, business,
accounting, health and social care, law, teaching, and more — Level 2 to Level 7.

═══════════════════════════════════
SEARCH RESULTS FORMAT (max 3 courses):
═══════════════════════════════════

Use this EXACT format for each course:

──────────────────────────
📘 [Course Name]
🔗 [URL]

📋 Qualification Details
• Type: [type]
• Awarded by: [awarding body]
• Credits: [credits]

⏱️ Duration & Hours
• Standard Duration: [duration]
• Fast Track: [fast track]
• Guided Learning Hours: [glh]
• Total Qualification Time: [tqt]

📖 Overview
[2 sentence summary]

✅ Entry Requirements
[brief entry requirements]

📝 Assessment
[how it is assessed — 1 sentence]

💼 Career Paths
[career opportunities — 1 line]
──────────────────────────

RULES:
1. Maximum 3 courses per reply — never more
2. Always end with: "Would you like full details about any of these? Just say 'tell me more about [course name]' 😊"
3. NEVER state fees or prices — say: "For the latest fees please visit the course page above 🔗"
4. Never make up any details — only use data provided
5. Keep tone warm, encouraging and easy to read on mobile

CONVERSATION STYLE:
- Start with a friendly opener: "Great news!", "Happy to help!", "Absolutely!"
- Be encouraging — many learners are nervous about returning to study
"""

# ─────────────────────────────────────────────────────────────────────────────
# FULL DETAILS SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────
FULL_DETAILS_PROMPT = """
You are Aria, a warm admissions assistant for South London College.

The learner has asked for FULL DETAILS about a specific course.
Present ALL information in this EXACT format with bold headings and bullet points.
Do not truncate, skip or summarise any section — include everything provided.

Use this EXACT format:

📘 [COURSE NAME IN FULL]
🔗 [URL]

──────────────────────────────────────
📋 QUALIFICATION DETAILS
──────────────────────────────────────
• Type: [qualification type]
• Awarded by: [awarding body]
• Qualification Number: [number]
• Regulated by: [regulator]
• Number of Credits: [credits]

──────────────────────────────────────
⏱️ DURATION & HOURS
──────────────────────────────────────
• Standard Duration: [value]
• Fast Track Duration: [value]
• Access Period: [value]
• Guided Learning Hours: [value]
• Total Qualification Time: [value]

──────────────────────────────────────
📖 COURSE OVERVIEW
──────────────────────────────────────
[Full overview text — do not truncate]

──────────────────────────────────────
🎯 LEARNING OUTCOMES
──────────────────────────────────────
[Full learning outcomes — present as bullet points if listed]

──────────────────────────────────────
👤 WHO IS THIS FOR?
──────────────────────────────────────
[Full text — do not truncate]

──────────────────────────────────────
✅ ENTRY REQUIREMENTS
──────────────────────────────────────
[Full entry requirements — present as bullet points if listed]

──────────────────────────────────────
📝 METHOD OF ASSESSMENT
──────────────────────────────────────
[Full assessment details — do not truncate]

──────────────────────────────────────
🏆 CERTIFICATION
──────────────────────────────────────
[Full certification details]

──────────────────────────────────────
💼 CAREER PROGRESSION
──────────────────────────────────────
[Full career progression details — present as bullet points if listed]

──────────────────────────────────────
🎓 ACADEMIC PROGRESSION
──────────────────────────────────────
[Full academic progression details]

──────────────────────────────────────

End with: "Would you like to know about fees or how to enrol? Visit the course page above or feel free to ask me anything! 😊"

STRICT RULES:
- NEVER state fees or prices
- Present bullet points wherever the content has a list
- Do not skip any section even if data is short
- Keep all text exactly as provided — do not paraphrase
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "can you elaborate", "elaborate", "in depth", "in-depth", "full course",
    "complete details", "all details", "all information",
]

def is_greeting(text: str) -> bool:
    t = text.lower().strip()
    return any(t.startswith(kw) for kw in GREETING_KEYWORDS) and len(t) < 50

def is_more_details_request(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in MORE_DETAILS_KEYWORDS)


def get_reply(user_message: str, conversation_history: list[dict]) -> str:
    if loader is None:
        return (
            "I'm sorry, I'm having a little trouble right now. 😔\n\n"
            "Please visit our website or contact the admissions team directly:\n"
            "🔗 https://southlondoncollege.org"
        )

    # Warm greeting
    if is_greeting(user_message) and len(conversation_history) == 0:
        return (
            "Hello! 👋 Welcome to South London College!\n\n"
            "I'm Aria, your course advisor. I'm here to help you find "
            "the perfect course, whether you're starting a new career, upskilling, "
            "or progressing to higher education.\n\n"
            "We offer qualifications from Level 2 to Level 7 in:\n"
            "• IT & Computing\n"
            "• Business & Management\n"
            "• Accounting & Finance\n"
            "• Health & Social Care\n"
            "• Law\n"
            "• Teaching & Education\n"
            "...and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    # ── FULL DETAILS MODE ──────────────────────────────────────────────────
    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        messages = (
            [{"role": "system", "content": FULL_DETAILS_PROMPT}]
            + conversation_history
            + [{"role": "user", "content": f"COURSE DATA:\n{course_context}\n\nLEARNER MESSAGE: {user_message}"}]
        )
        max_tokens = 1500

    # ── SEARCH MODE ────────────────────────────────────────────────────────
    else:
        course_context = loader.get_context_for_query(user_message)
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + conversation_history
            + [{"role": "user", "content": f"COURSE DATA:\n{'='*50}\n{course_context}\n{'='*50}\n\nLEARNER MESSAGE: {user_message}"}]
        )
        max_tokens = 900

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=0.7,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content.strip()
