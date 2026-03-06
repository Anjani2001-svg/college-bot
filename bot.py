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
    print(f"Loaded {len(loader.df)} courses from {COURSES_PATH}")
except FileNotFoundError as e:
    print(f"ERROR: {e}")
    loader = None

SYSTEM_PROMPT = """
You are Aria, a warm and friendly admissions assistant for South London College.
Your job is to help learners find the right course and feel excited about studying.

South London College offers courses in IT, computing, cyber security, business,
accounting, health and social care, law, teaching, and more - Level 2 to Level 7.

HOW TO FORMAT SEARCH RESULTS (max 3 courses):

Use this EXACT format for each course:

──────────────────────────
📘 [COURSE NAME IN CAPITALS]
Overview: [2 sentences summarising what the course covers]
Level: [level] | Duration: [standard] (Fast Track: [fast track])
Guided Learning Hours: [hours] | Credits: [credits]
Best for: [one sentence who its for]
Entry Requirements: [brief entry requirements]
Assessment: [how the course is assessed in one line]
Career Paths: [one line about jobs after completing]
🔗 [full URL on its own line]
──────────────────────────

After listing courses always end with:
"Would you like full details about any of these? Just say tell me more about [course name] 😊"

FULL DETAILS MODE:
When you receive a FULL DETAILS block, output it EXACTLY as provided.
Do not rewrite, summarise or change the formatting.
Just present it cleanly and end with:
"Would you like to know about fees or how to enrol? 😊"

STRICT RULES:
1. NEVER state a price or fee - say: For the latest pricing please visit the course page
2. Never make up course details
3. Max 3 courses per search reply
4. Keep tone warm and encouraging
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "in depth", "in-depth", "full course", "complete details", "all details",
]

def is_greeting(text: str) -> bool:
    t = text.lower().strip()
    return any(t.startswith(kw) for kw in GREETING_KEYWORDS) and len(t) < 50

def is_more_details_request(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in MORE_DETAILS_KEYWORDS)


def get_reply(user_message: str, conversation_history: list) -> str:
    if loader is None:
        return (
            "I am sorry, I am having a little trouble right now.\n\n"
            "Please visit our website or contact the admissions team directly:\n"
            "🔗 https://southlondoncollege.org"
        )

    if is_greeting(user_message) and len(conversation_history) == 0:
        return (
            "Hello! 👋 Welcome to South London College!\n\n"
            "I am Aria, your course advisor. I am here to help you find "
            "the perfect course, whether you are starting a new career, upskilling, "
            "or progressing to higher education.\n\n"
            "We offer qualifications from Level 2 to Level 7 in:\n"
            "• IT & Computing\n"
            "• Business & Management\n"
            "• Accounting & Finance\n"
            "• Health & Social Care\n"
            "• Law\n"
            "• Teaching & Education\n"
            "• and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        mode_note = "FULL DETAILS MODE: Output the course data block exactly as provided. Do not summarise."
        max_tok = 1500
    else:
        course_context = loader.get_context_for_query(user_message)
        mode_note = "SEARCH MODE: Show max 3 matching courses in the standard format."
        max_tok = 800

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
        max_tokens=max_tok,
    )

    return response.choices[0].message.content.strip()
