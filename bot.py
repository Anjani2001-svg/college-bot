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

CORE BEHAVIOUR
- Be warm, encouraging and get to the point quickly
- Use the FULL conversation history — never forget what was said earlier
- If learner mentions any subject or interest, suggest matching courses immediately
- Only ask ONE follow-up question maximum before showing courses
- If someone asks about fees: say fees vary and direct them to the course page
- If someone asks how to enrol: explain they can visit the course page or contact admissions

COURSE CARD FORMAT — use this EXACTLY for search results (max 3 courses):

──────────────────────────
📘 [Course Name]

[Level]  •  Awarded by: [body]  •  [Regulated]
[Standard duration]  |  Fast Track: [fast track]  |  [Credits] Credits

What you will learn:
→ [outcome 1]
→ [outcome 2]
→ [outcome 3 — max 3]

Who it is for: [one line]
Entry: [one line]
Assessment: [one line — note if no exams]

Career Paths:
→ [Job] — [salary]
→ [Job] — [salary]

Academic Progression: [one line next step]

🔗 [URL]
──────────────────────────

After listing courses always end with:
"Want full details? Just say tell me more about [course name] 😊"

STRICT RULES
- NEVER state a price or fee
- Never make up course details
- Max 3 courses per reply
- Keep tone warm and concise
"""

GREETING_KEYWORDS = [
    "hi", "hello", "hey", "good morning", "good afternoon",
    "good evening", "hiya", "howdy",
]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "in depth", "in-depth", "full course", "complete details", "all details",
    "tell me more about this", "more about this",
    "about that course", "that one", "first one", "second one", "third one",
    "the first", "the second", "the third", "show me more", "expand on",
    "send more", "more on this", "more on that",
]

COURSE_SEARCH_KEYWORDS = [
    "course", "courses", "qualification", "diploma", "certificate",
    "do you have", "do you offer", "what courses", "show me", "find me",
    "looking for", "interested in", "what do you offer", "available courses",
    "recommend", "computing", "accounting", "teaching", "management", "cyber",
    "programming", "software", "java", "python", "coding", "developer",
    "law", "health", "care", "business", "finance", "marketing", "hr",
    "psychology", "counselling", "childcare", "logistics", "hospitality",
    "related", "any courses", "similar", "is there", "are there",
    "can i study", "can i learn",
]

CONVERSATION_OVERRIDE_KEYWORDS = [
    "how to enrol", "how do i enrol", "how to apply", "how do i apply",
    "what are the fees", "how much", "what is the cost", "cost of",
    "when does it start", "start date", "when can i start",
    "is this course good", "is it good", "is it worth", "worth it",
    "should i do", "should i take", "what do you think",
    "is it hard", "is it difficult", "good for me", "right for me",
    "suits me", "good choice", "what else", "anything else",
    "can you tell me more", "what about this",
]

FOLLOWUP_PHRASES = [
    "related this", "related to this", "courses related", "any courses",
    "is there any", "are there any", "something like", "similar courses",
    "anything related",
]


def is_greeting(text):
    t = text.lower().strip()
    return any(t.startswith(kw) for kw in GREETING_KEYWORDS) and len(t) < 50


def is_more_details_request(text):
    t = text.lower().strip()
    return any(kw in t for kw in MORE_DETAILS_KEYWORDS)


def is_conversation_override(text):
    t = text.lower().strip()
    return any(kw in t for kw in CONVERSATION_OVERRIDE_KEYWORDS)


def is_course_search(text):
    t = text.lower().strip()
    if is_conversation_override(t):
        return False
    return any(kw in t for kw in COURSE_SEARCH_KEYWORDS)


def is_vague_followup(text):
    t = text.lower().strip()
    return any(phrase in t for phrase in FOLLOWUP_PHRASES)


def build_context_query(current_msg, history):
    recent = []
    for msg in history[-6:]:
        text = msg.get("content", "").strip()
        if text and len(text) > 5:
            recent.append(text[:150])
    if recent:
        return current_msg + " " + " ".join(recent)
    return current_msg


def get_reply(user_message: str, conversation_history: list) -> str:
    if loader is None:
        return (
            "I am sorry, I am having a little trouble right now.\n\n"
            "Please visit our website: https://southlondoncollege.org"
        )

    # ── Greeting ──────────────────────────────────────────────────
    if is_greeting(user_message) and len(conversation_history) == 0:
        return (
            "Hello! Welcome to South London College!\n\n"
            "I am Aria, your course advisor. I am here to help you find "
            "the perfect course.\n\n"
            "We offer Level 2 to Level 7 qualifications in:\n"
            "→ IT & Computing\n"
            "→ Business & Management\n"
            "→ Accounting & Finance\n"
            "→ Health & Social Care\n"
            "→ Law\n"
            "→ Teaching & Education and much more!\n\n"
            "What are you interested in studying? 😊"
        )

    # ── CONVERSATION OVERRIDE — check FIRST before any course logic ──
    # Catches: "is this course good?", "how to enrol", fees, opinions
    # These must never trigger full details or course search
    if is_conversation_override(user_message):
        course_context = ""
        mode_note = (
            "CONVERSATION MODE: The learner is asking a question that needs "
            "a conversational answer — e.g. opinion on a course, fees, enrolment. "
            "Use conversation history to understand context and give a warm, "
            "helpful, specific reply. Do NOT show course listings."
        )
        max_tok = 450

    # ── MODE 1: FULL DETAILS — bypass GPT, return directly ────────
    elif is_more_details_request(user_message):
        search_query = build_context_query(user_message, conversation_history)
        full_details = loader.get_full_details_for_query(search_query)

        if "No matching" not in full_details:
            return (
                full_details.strip()
                + "\n\n"
                + "Ready to take the next step? Visit the course page or contact our admissions team 😊"
            )

    # ── MODE 2: COURSE SEARCH ──────────────────────────────────────
    elif is_course_search(user_message):
        search_query = (
            build_context_query(user_message, conversation_history)
            if is_vague_followup(user_message)
            else user_message
        )
        course_context = loader.get_context_for_query(search_query)
        mode_note = "SEARCH MODE: Show max 3 matching courses using the standard card format."
        max_tok = 1000

    # ── MODE 3: CONVERSATION ───────────────────────────────────────
    elif not is_conversation_override(user_message):
        course_context = ""
        mode_note = (
            "CONVERSATION MODE: Reply naturally and warmly. "
            "Use conversation history for context. "
            "If learner's topic hints at a subject interest, suggest showing courses. "
            "Do NOT show full course listings unless asked."
        )
        max_tok = 450

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation_history
        + [
            {
                "role": "user",
                "content": (
                    f"[MODE: {mode_note}]\n\n"
                    + (
                        f"[COURSE DATA]:\n{'─' * 40}\n{course_context}\n{'─' * 40}\n\n"
                        if course_context
                        else ""
                    )
                    + f"LEARNER: {user_message}"
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
