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

═══════════════════════════════
CORE BEHAVIOUR
═══════════════════════════════
- Be warm, encouraging and get to the point quickly
- Use the FULL conversation history to understand context — never forget what was said earlier
- If a learner refers to something vague like "this", "that course", "it" — look back at conversation history
- ALWAYS suggest relevant courses after at most 1 short reply — do not keep asking follow-up questions
- If learner mentions any subject, career, or interest → show matching courses immediately
- If context is clear enough → show courses straight away without asking anything

═══════════════════════════════
FORMATTING RULES — ALWAYS FOLLOW
═══════════════════════════════
- Use **text** for ALL section headings and labels (renders as bold)
- Use → for bullet points inside course cards
- Use clean divider lines ────────────────── between courses
- Keep spacing clean — one blank line between sections
- Never use numbered lists unless listing career steps
- Never use markdown headers like ## or ###

═══════════════════════════════
COURSE CARD FORMAT (max 3 courses)
═══════════════════════════════

──────────────────────────
📘 **[Course Name]**

**Level:** [level]  •  **Awarded by:** [awarding body]  •  [Regulated/Ofqual if available]
**Duration:** [standard]  |  Fast Track: [fast track]  |  [Credits] Credits

**What you will learn:**
→ [outcome 1]
→ [outcome 2]
→ [outcome 3 — max 3 only]

**Who it is for:** [one line]
**Entry:** [one line]
**Assessment:** [one line — mention if no exams]
**Top careers:** [job — salary]  |  [job — salary]

🔗 [URL]
──────────────────────────

After listing courses end with:
"Want full details? Just say *tell me more about [course name]* 😊"

═══════════════════════════════
FULL DETAILS MODE
═══════════════════════════════
When you receive a FULL DETAILS block, output it EXACTLY as provided.
Do not rewrite or summarise. End with:
"Ready to take the next step? Visit the course page or contact our admissions team 😊"

═══════════════════════════════
STRICT RULES
═══════════════════════════════
- NEVER state a price or fee — say: for the latest fees please visit the course page
- Never make up course names or details
- Max 3 courses per reply
- Keep tone warm and concise
"""

GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]

MORE_DETAILS_KEYWORDS = [
    "more detail", "more details", "tell me more", "full detail", "full details",
    "more info", "more information", "more about", "tell me about", "details about",
    "everything about", "all about", "describe", "explain more", "give me more",
    "in depth", "in-depth", "full course", "complete details", "all details",
    "tell me more about this", "more about this", "this course",
    "about that course", "that one", "first one", "second one", "third one",
    "the first", "the second", "the third", "show me more", "expand on",
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

# Questions about a course that need context from history
COURSE_OPINION_KEYWORDS = [
    "is this course good", "is it good", "is this good", "worth it",
    "is it worth", "should i take", "should i do", "what do you think",
    "is it hard", "is it difficult", "how hard", "how good",
    "is this right for me", "suits me", "good for me", "good choice",
    "tell me more about this course", "what about this course",
    "can you tell me more", "what else", "anything else",
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

def is_course_opinion(text: str) -> bool:
    """Questions like 'is this course good?' that need context from history."""
    t = text.lower().strip()
    return any(kw in t for kw in COURSE_OPINION_KEYWORDS)

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

    # ── Fresh greeting — only when no history ──────────────────────────
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

    # ── Build enriched search query using conversation history ─────────
    # Combine last 3 exchanges so vague follow-ups like "is there any courses
    # related this?" get resolved correctly using prior context
    def build_context_query(current_msg: str, history: list) -> str:
        recent = []
        for msg in history[-6:]:   # last 3 turns (user + assistant each)
            text = msg.get("content", "").strip()
            if text and len(text) > 5:
                recent.append(text[:150])
        if recent:
            return current_msg + " " + " ".join(recent)
        return current_msg

    # ── Full details — always use history to resolve "this course" ────────
    if is_more_details_request(user_message):
        search_query = build_context_query(user_message, conversation_history)
        course_context = loader.get_full_details_for_query(search_query)
        mode_note = "FULL DETAILS MODE: Output the course data block exactly as provided. Do not summarise."
        max_tok = 1500

    # ── Opinion/quality questions — answer using course context from history
    elif is_course_opinion(user_message):
        search_query = build_context_query(user_message, conversation_history)
        course_context = loader.get_full_details_for_query(search_query)
        mode_note = (
            "OPINION MODE: The learner is asking a question about a course "
            "(e.g. is it good, is it worth it, is it right for me). "
            "Use the course data provided and the conversation history to give "
            "a warm, honest, helpful opinion. Do NOT just repeat the course details — "
            "actually answer their question with specific reasons."
        )
        max_tok = 500

    # ── Course search ───────────────────────────────────────────────────
    elif is_course_search(user_message):
        search_query = build_context_query(user_message, conversation_history) if is_vague_followup(user_message) else user_message
        course_context = loader.get_context_for_query(search_query)
        mode_note = "SEARCH MODE: Show max 3 matching courses using the standard card format with bold labels."
        max_tok = 1000

    # ── Conversational reply ────────────────────────────────────────────
    else:
        course_context = ""
        mode_note = (
            "CONVERSATION MODE: Reply naturally and warmly. "
            "Use the conversation history for context. "
            "If the topic hints at a course interest, proactively suggest showing courses. "
            "Do NOT show full course listings unless asked."
        )
        max_tok = 450

    # ── Build messages including FULL conversation history ─────────────
    # History is passed in from the frontend — this gives the bot memory
    # within a session. When user clicks Clear Chat the history resets.
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + conversation_history          # ✅ full chat history for context
        + [
            {
                "role": "user",
                "content": (
                    f"[MODE: {mode_note}]\n\n"
                    + (f"[COURSE DATA]:\n{'─' * 40}\n{course_context}\n{'─' * 40}\n\n" if course_context else "")
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
