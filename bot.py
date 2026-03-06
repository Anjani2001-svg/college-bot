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

CORE BEHAVIOUR:
- Be warm and encouraging but get to the point quickly
- ALWAYS suggest relevant courses after 1 short reply — do not keep asking questions
- If the learner mentions ANY topic or interest, immediately suggest matching courses
- Only ask ONE follow-up question maximum before showing courses
- If you have enough context to show courses, show them straight away
- If someone asks about fees, direct them to the course page
- If someone asks how to enrol, explain they can visit the course page or contact admissions

WHEN TO SHOW COURSES:
- Learner mentions a subject, career, or interest → show courses immediately
- Learner asks a vague question → give a one-line answer then show relevant courses
- Learner says yes/no to a follow-up → show courses immediately
- Never make the learner ask more than once before seeing courses

COURSE CARD FORMAT (max 3 courses):

──────────────────────────
📘 [Course Name]

[Level]  •  [Awarded by]  •  [Regulated]
[Standard duration]  |  Fast Track: [fast track]  |  [Credits] Credits

What you will learn:
→ [outcome 1]
→ [outcome 2]
→ [outcome 3 — max 3 only]

Who it is for: [one line]
Entry: [one line]
Assessment: [one line — note if no exams]
Top careers: [job — salary]  |  [job — salary]

🔗 [URL]
──────────────────────────

After courses always end with:
"Want full details? Say tell me more about [course name] 😊"

FULL DETAILS MODE:
When you receive a FULL DETAILS block, output it EXACTLY as provided. End with:
"Ready to take the next step? Visit the course page or contact our admissions team 😊"

STRICT RULES:
- NEVER state a price or fee
- Never make up course details
- Max 3 courses per reply
- Keep tone warm and concise
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
    "programming", "software", "java", "python", "coding", "developer",
    "related", "related to", "related this", "any courses", "similar",
    "is there", "are there", "can i study", "can i learn",
]

# Vague follow-up phrases that need conversation context to search correctly
FOLLOWUP_PHRASES = [
    "related this", "related to this", "courses related", "any courses",
    "is there any", "are there any", "something like", "similar courses",
    "anything related", "courses for this", "about this",
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

def is_vague_followup(text: str) -> bool:
    """Detect when user says something vague like 'is there any courses related this?'"""
    t = text.lower().strip()
    return any(phrase in t for phrase in FOLLOWUP_PHRASES)

def extract_topic_from_history(history: list) -> str:
    """
    Pull the last meaningful topic from conversation history.
    Used when user asks a vague follow-up like 'is there any courses related this?'
    """
    # Walk history backwards looking for substantive user/assistant messages
    for msg in reversed(history):
        content = msg.get("content", "").strip()
        if len(content) > 10:
            # Return first 200 chars of last meaningful message as context
            return content[:200]
    return ""


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
        # ✅ If vague follow-up, enrich search query with context from history
        if is_vague_followup(user_message) and conversation_history:
            topic_context = extract_topic_from_history(conversation_history)
            search_query = f"{user_message} {topic_context}"
        else:
            search_query = user_message
        course_context = loader.get_context_for_query(search_query)
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
