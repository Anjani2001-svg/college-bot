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
Your job is to have natural conversations with learners and help them find courses.

CONVERSATION RULES:
- Be warm, friendly and conversational
- Do NOT show course listings unless the learner is clearly asking about courses
- If someone asks a general question, answer it naturally
- Only show course cards when the learner asks about specific courses
- If someone asks about fees, say fees vary and direct them to the course page
- If someone asks how to enrol, explain they can visit the course page or contact admissions
- Ask follow-up questions to understand what the learner needs
- Keep replies short and natural unless showing course details

WHEN SHOWING SEARCH RESULTS use this EXACT format (max 3 courses):

──────────────────────────
📘 [COURSE NAME IN CAPITALS]

🎓 [Level]  •  [Awarded by]  •  [Regulated if available]
⏱️ [Standard duration]  •  Fast Track: [fast track]  •  [Credits] Credits

What you will learn:
→ [outcome 1]
→ [outcome 2]
→ [outcome 3 - max 3 outcomes only]

Who it is for: [one line description]

Entry: [brief entry requirements in one line]

Assessment: [one line - mention if no exams]

Top careers: [job 1 with salary]  |  [job 2 with salary]

🔗 [URL]
──────────────────────────

After listing courses always end with:
"Want full details on any of these? Just say tell me more about [course name] 😊"

FULL DETAILS MODE:
When you receive a FULL DETAILS block, output it EXACTLY as provided.
Do not rewrite or summarise. End with:
"Ready to take the next step? Visit the course page or contact our admissions team 😊"

STRICT RULES:
- NEVER state a price or fee
- Never make up course details
- Max 3 courses per search reply
- Keep tone warm and encouraging
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "in depth", "in-depth", "full course", "complete details", "all details",
]

COURSE_SEARCH_KEYWORDS = [
    "course", "courses", "qualification", "diploma", "certificate", "level",
    "study", "studying", "learn", "learning", "enrol", "enroll",
    "do you have", "do you offer", "what courses", "show me", "find me",
    "i want to", "i would like to", "looking for", "interested in",
    "it course", "business course", "health course", "law course",
    "computing", "accounting", "teaching", "management", "cyber",
    "what do you offer", "available courses", "recommend",
]

def is_greeting(text: str) -> bool:
    t = text.lower().strip()
    return any(t.startswith(kw) for kw in GREETING_KEYWORDS) and len(t) < 50

def is_more_details_request(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in MORE_DETAILS_KEYWORDS)

def is_course_search(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in COURSE_SEARCH_KEYWORDS)


def get_reply(user_message: str, conversation_history: list) -> str:
    if loader is None:
        return (
            "I am sorry, I am having a little trouble right now.\n\n"
            "Please visit our website: 🔗 https://southlondoncollege.org"
        )

    if is_greeting(user_message) and len(conversation_history) == 0:
        return (
            "Hello! 👋 Welcome to South London College!\n\n"
            "I am Aria, your course advisor. I am here to help you find "
            "the perfect course — whether you are starting fresh, upskilling, "
            "or progressing to higher education.\n\n"
            "We offer Level 2 to Level 7 qualifications in:\n"
            "→ IT & Computing\n"
            "→ Business & Management\n"
            "→ Accounting & Finance\n"
            "→ Health & Social Care\n"
            "→ Law\n"
            "→ Teaching & Education and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        mode_note = "FULL DETAILS MODE: Output the course data block exactly as provided."
        max_tok = 1500

    elif is_course_search(user_message):
        course_context = loader.get_context_for_query(user_message)
        mode_note = "SEARCH MODE: Show max 3 matching courses in the standard card format."
        max_tok = 900

    else:
        course_context = ""
        mode_note = "CONVERSATION MODE: Reply naturally. Do NOT show course listings."
        max_tok = 400

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation_history
        + [
            {
                "role": "user",
                "content": (
                    f"MODE: {mode_note}\n\n"
                    + (f"COURSE DATA:\n{'=' * 40}\n{course_context}\n{'=' * 40}\n\n" if course_context else "")
                    + f"LEARNER MESSAGE: {user_message}"
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
