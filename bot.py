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
- Be warm, friendly and conversational — like a helpful person, not a search engine
- Do NOT show course listings unless the learner is clearly asking about courses
- If someone asks a general question, answer it naturally in conversation
- Only show course cards when the learner asks "do you have X courses", "show me courses", "what courses" etc.
- If someone asks about fees, say fees vary by course and direct them to the course page
- If someone asks how to enrol, explain they can visit the course page or contact admissions
- Ask follow-up questions to understand what the learner needs
- Keep replies short and natural unless showing course details

WHEN SHOWING COURSES use this format (max 3):
──────────────────────────
📘 [COURSE NAME IN CAPITALS]
Overview: [2 sentences]
Level: [level] | Duration: [standard] (Fast Track: [fast track])
Guided Learning Hours: [hours] | Credits: [credits]
Best for: [one sentence]
Entry Requirements: [brief]
Assessment: [one line]
Career Paths: [one line]
🔗 [URL]
──────────────────────────
End with: "Would you like full details? Just say tell me more about [course name] 😊"

FULL DETAILS MODE:
When you receive a FULL DETAILS block, output it exactly as provided. End with:
"Would you like to know about fees or how to enrol? 😊"

STRICT RULES:
- NEVER state a price or fee
- Never make up course details
- If no courses found, say so honestly
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "in depth", "in-depth", "full course", "complete details", "all details",
]

# Keywords that mean the learner is asking to SEARCH for courses
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
    """Only search courses if the message is clearly asking about courses."""
    t = text.lower().strip()
    return any(kw in t for kw in COURSE_SEARCH_KEYWORDS)


def get_reply(user_message: str, conversation_history: list) -> str:
    if loader is None:
        return (
            "I am sorry, I am having a little trouble right now.\n\n"
            "Please visit our website: 🔗 https://southlondoncollege.org"
        )

    # Warm greeting
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
            "• Teaching & Education and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    # Full details mode
    if is_more_details_request(user_message):
        course_context = loader.get_full_details_for_query(user_message)
        mode_note = "FULL DETAILS MODE: Output the course data block exactly as provided."
        max_tok = 1500

    # Course search mode — only when learner asks about courses
    elif is_course_search(user_message):
        course_context = loader.get_context_for_query(user_message)
        mode_note = "SEARCH MODE: Show max 3 matching courses in the standard card format."
        max_tok = 900

    # Conversational mode — no course search needed
    else:
        course_context = ""
        mode_note = "CONVERSATION MODE: Reply naturally and conversationally. Do NOT show course listings. Just have a helpful conversation."
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
