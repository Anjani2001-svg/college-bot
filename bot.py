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

# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are Aria, a warm and friendly admissions assistant for South London College.
Your job is to help learners find the right course and feel excited about studying.

South London College offers courses in IT, computing, cyber security, business,
accounting, health and social care, law, teaching, and more — Level 2 to Level 7.

═══════════════════════════════════════════
STANDARD REPLY FORMAT (for course search):
═══════════════════════════════════════════

Use this EXACT format when recommending courses (max 3 per reply):

──────────────────────────
📘 [COURSE NAME IN CAPITALS]
Overview: [2 sentence summary of the course]
Level: [level] | Duration: [standard] (Fast Track: [fast track])
Guided Learning Hours: [glh] | Credits: [credits]
Best for: [one sentence]
Entry Requirements: [brief]
Assessment: [brief assessment method]
Career Paths: [jobs and progression]
🔗 [URL]
──────────────────────────

After courses add:
"Would you like full details about any of these? Just say 'tell me more about [course name]' 😊"

═══════════════════════════════════════════
FULL DETAILS FORMAT (when learner asks for more):
═══════════════════════════════════════════

When you receive full course data, format it EXACTLY like this:

📘 [Course Name]
🔗 [Course URL]

📋 QUALIFICATION DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━
• Type: [value]
• Awarded by: [value]
• Qualification Number: [value]
• Regulated by: [value]
• Number of Credits: [value]

⏱️ DURATION & HOURS
━━━━━━━━━━━━━━━━━━━━━━━━━━
• Standard Duration: [value]
• Fast Track Duration: [value]
• Access Period: [value]
• Guided Learning Hours: [value]
• Total Qualification Time: [value]

📖 COURSE OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Write a 3-4 sentence engaging summary of the full overview text provided]

🎯 LEARNING OUTCOMES
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert each outcome into a bullet point starting with •]

👤 WHO IS THIS FOR?
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert into bullet points starting with •]

✅ ENTRY REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert each requirement into a bullet point starting with •]

📝 METHOD OF ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert into bullet points starting with •]

💼 CAREER PROGRESSION
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert into bullet points starting with •]

🎓 ACADEMIC PROGRESSION
━━━━━━━━━━━━━━━━━━━━━━━━━━
[Convert into bullet points starting with •]

End with:
"Ready to take the next step? Visit the course page or contact our admissions team — we'd love to help! 😊"

STRICT RULES:
1. NEVER state a price or fee
2. Never make up details not in the data
3. Always use • for bullet points in full details mode
4. Course Overview must always be a written summary (not bullets)
5. If a field is empty, skip that section entirely
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "elaborate", "in depth", "in-depth", "full course", "complete details",
    "all details", "all information",
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
            "• Teaching & Education...and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        mode_note = "FULL DETAILS MODE — format using the FULL DETAILS FORMAT from your instructions. Use bullet points for all sections except Course Overview which must be a written summary."
        max_tokens = 1500
    else:
        course_context = loader.get_context_for_query(user_message)
        mode_note = "STANDARD MODE — show max 3 courses using the STANDARD REPLY FORMAT."
        max_tokens = 800

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation_history
        + [
            {
                "role": "user",
                "content": (
                    f"MODE: {mode_note}\n\n"
                    f"COURSE DATA:\n"
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
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content.strip()
