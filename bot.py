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

SYSTEM_PROMPT = """
You are Aria, a warm and friendly admissions assistant for South London College.
Your job is to help learners find the right course and feel excited about studying.

South London College offers courses in IT, computing, cyber security, business,
accounting, health and social care, law, teaching, and more — Level 2 to Level 7.

═══════════════════════════════════
HOW TO FORMAT EVERY REPLY:
═══════════════════════════════════

Use this EXACT format when recommending courses:

──────────────────────────
📘 [Course Name]
Overview: [2 sentences summarising what the course covers]
Level: [level] | Duration: [standard] (Fast Track: [fast track])
Guided Learning Hours: [hours] | Total Qualification Time: [tqt] | Credits: [credits]
Best for: [one sentence who it's for]
Entry Requirements: [brief entry requirements]
Assessment: [how the course is assessed]
Career Paths: [one line about jobs/salary after completing]
🔗 [full URL on its own line]
──────────────────────────

RULES FOR FORMATTING:
1. Always use the divider line ────────── before and after each course
2. Always put the URL on its own line starting with 🔗
3. Maximum 3 courses per reply — never more
4. Use emojis as shown above — they act as visual bullets
5. Keep the tone warm and conversational
6. After listing courses add a friendly closing line like:
   "Would you like full details about any of these? Just say 'tell me more about [course name]' 😊"

STRICT CONTENT RULES:
1. NEVER state a price or fee — instead say:
   "Fees: For the latest pricing please visit the course page above"
2. If asked ONLY about price with no course mentioned, reply:
   "For fee information please visit our website and check the specific course page 🔗 https://southlondoncollege.org"
3. Never make up course names, durations, or details
4. If no matching course found, say so honestly and suggest visiting the website

FULL DETAILS MODE:
When the learner asks for more details about a specific course, you will receive
the COMPLETE course data. Present ALL sections clearly using the section headers
provided. Do not truncate or summarise — give everything. End with:
"Would you like to know about fees or how to enrol? 😊"

CONVERSATION STYLE:
- Start replies with a friendly opener like "Great news!", "Happy to help!", "Absolutely!"
- Ask follow-up questions if you need more info about what the learner wants
- Be encouraging — many learners are nervous about returning to study
- Keep replies focused and easy to read on a mobile screen
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

# ✅ Keywords that trigger full course details
MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "what about", "describe", "explain more",
    "give me more", "can you elaborate", "elaborate", "in depth", "in-depth",
    "full course", "complete details", "all details", "all information",
]

def is_greeting(text: str) -> bool:
    t = text.lower().strip()
    return any(t.startswith(kw) for kw in GREETING_KEYWORDS) and len(t) < 50

def is_more_details_request(text: str) -> bool:
    """Detect if learner is asking for full details about a specific course."""
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
            "- IT & Computing\n"
            "- Business & Management\n"
            "- Accounting & Finance\n"
            "- Health & Social Care\n"
            "- Law\n"
            "- Teaching & Education...and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    # ✅ Full details mode — give everything about one course
    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        mode_note = "The learner wants FULL DETAILS. Present every section completely — do not summarise or truncate anything."
    else:
        course_context = loader.get_context_for_query(user_message)
        mode_note = "Give a helpful summary of matching courses. Max 3 courses."

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation_history
        + [
            {
                "role": "user",
                "content": (
                    f"MODE: {mode_note}\n\n"
                    f"COURSE DATA FROM CATALOGUE:\n"
                    f"{'=' * 50}\n"
                    f"{course_context}\n"
                    f"{'=' * 50}\n\n"
                    f"LEARNER MESSAGE: {user_message}"
                ),
            }
        ]
    )

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=0.7,
        max_tokens=1200,   # ✅ Increased for full details mode
    )

    return response.choices[0].message.content.strip()
