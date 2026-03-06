import re
import pandas as pd
from pathlib import Path

SYNONYMS = {
    "it":             ["computing", "digital", "technology", "information"],
    "tech":           ["computing", "digital", "technology", "information"],
    "computer":       ["computing", "digital", "technology"],
    "computers":      ["computing", "digital", "technology"],
    "coding":         ["programming", "computing", "software", "developer"],
    "code":           ["programming", "computing", "software"],
    "web":            ["web development", "digital", "computing"],
    "cyber":          ["cyber security", "computing", "digital"],
    "security":       ["cyber security", "computing"],
    "data":           ["data analyst", "computing", "digital"],
    "software":       ["software developer", "computing", "programming"],
    "finance":        ["accounting", "finance"],
    "money":          ["accounting", "finance"],
    "hr":             ["human resources", "business"],
    "health":         ["health", "social care", "healthcare"],
    "care":           ["social care", "health", "adult care"],
    "nurse":          ["health", "social care", "nursing"],
    "teach":          ["teaching", "education", "teacher"],
    "teacher":        ["teaching", "education", "foundations of teaching"],
    "law":            ["law", "legal"],
    "legal":          ["law", "legal"],
    "management":     ["management", "business", "leadership"],
    "marketing":      ["marketing", "business", "digital"],
    "project":        ["project management", "business", "management"],
    "pm":             ["project management"],
    "leadership":     ["leadership", "management", "business"],
    "psychology":     ["psychology", "counselling", "mental health"],
    "mental":         ["mental health", "psychology", "counselling"],
    "maths":          ["mathematics", "maths", "functional skills"],
    "math":           ["mathematics", "maths", "functional skills"],
    "english":        ["english", "functional skills", "communication"],
    "sport":          ["sport", "physical education", "fitness"],
    "fitness":        ["fitness", "sport", "personal training"],
    "childcare":      ["childcare", "child", "early years"],
    "early years":    ["early years", "childcare"],
    "logistics":      ["logistics", "supply chain", "operations"],
    "supply chain":   ["supply chain", "logistics", "operations"],
    "hospitality":    ["hospitality", "hotel", "tourism"],
    "tourism":        ["tourism", "hospitality", "travel"],
    "hours":          ["guided learning hours", "total qualification time", "duration"],
    "guided":         ["guided learning hours", "learning hours"],
    "learning hours": ["guided learning hours", "total qualification time"],
    "credits":        ["number of credits", "credit", "qualification"],
    "credit":         ["number of credits", "credits", "qualification"],
    "tqt":            ["total qualification time", "guided learning hours"],
    "glh":            ["guided learning hours", "total qualification time"],
    "time":           ["total qualification time", "duration", "guided learning hours"],
    "outcomes":       ["learning outcomes", "what you will learn"],
    "units":          ["learning outcomes", "units", "modules"],
    "modules":        ["learning outcomes", "units", "modules"],
    "assessment":     ["method of assessment", "assessment", "portfolio"],
    "assessed":       ["method of assessment", "assessment"],
    "exam":           ["method of assessment", "assessment", "examination"],
    "portfolio":      ["method of assessment", "portfolio of evidence"],
    "certificate":    ["certification", "certificate", "qualification"],
    "regulated":      ["regulated by", "ofqual", "regulation"],
    "ofqual":         ["regulated by", "ofqual"],
    "accredited":     ["regulated by", "awarded by", "accredited"],
}


def _tokenize(text: str) -> set:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _expand_query(query: str) -> list:
    terms = []
    query_lower = query.lower().strip()
    for key, expansions in SYNONYMS.items():
        if key in query_lower:
            terms.extend(expansions)
    for word in re.findall(r"\b\w+\b", query_lower):
        if word not in ("the", "a", "an", "is", "are", "do", "does", "can", "any", "for", "in", "of", "and", "or", "to"):
            terms.append(word)
    return list(set(terms))


def _bullet(text: str, max_items: int = 99) -> str:
    """Convert newline-separated text into arrow bullet lines, optional max items."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return text.strip()
    if len(lines) == 1:
        return lines[0]
    return "\n".join(f"→ {l}" for l in lines[:max_items])


def _first_sentences(text: str, n: int = 2) -> str:
    """Return first n sentences of a paragraph."""
    text = text.replace("\n", " ").strip()
    parts = text.split(". ")
    result = ". ".join(parts[:n]).strip()
    if result and not result.endswith("."):
        result += "."
    return result


# ── Assessment method extraction ────────────────────────────
# Each entry: (search_pattern, canonical_display_label)
# Using canonical labels prevents duplicates entirely.
_ASSESSMENT_METHODS = [
    ("portfolio of evidence",    "Portfolio of Evidence"),
    ("written assignment",       "Written Assignments"),
    ("case stud",                "Case Studies"),
    ("practical assessment",     "Practical Assessments"),
    ("work-based project",       "Work-Based Project"),
    ("work based project",       "Work-Based Project"),
    ("reflective journal",       "Reflective Journals"),
    ("professional discussion",  "Professional Discussion"),
    ("observation",              "Observation"),
    ("online exam",              "Online Examination"),
    ("multiple choice",          "Multiple Choice"),
    ("short answer question",    "Short Answer Questions"),
    ("research project",         "Research Project"),
    ("presentation",             "Presentations"),
    ("report writing",           "Report Writing"),
    ("coursework",               "Coursework"),
    ("self-assessment",          "Self-Assessment"),
    ("peer assessment",          "Peer Assessment"),
    ("workplace evidence",       "Workplace Evidence"),
    ("witness testimony",        "Witness Testimony"),
]


def _extract_assessment_methods(text: str) -> list:
    """Pull only the core assessment method names — clean, deduplicated."""
    text_lower = text.lower()
    found = []
    seen_labels = set()

    for pattern, label in _ASSESSMENT_METHODS:
        if pattern in text_lower and label not in seen_labels:
            seen_labels.add(label)
            found.append(label)

    # Fallback: if nothing matched, return first 2 non-empty lines
    if not found:
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        return lines[:2]

    return found


# ── Career extraction helpers ───────────────────────────────

def _extract_career_intro(text: str, max_sentences: int = 3) -> str:
    """Return contextual intro lines (without salary figures)."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    intro_parts = []
    for line in lines:
        if "£" in line or "salary" in line.lower():
            continue
        intro_parts.append(line)
        if len(intro_parts) >= max_sentences:
            break
    return " ".join(intro_parts).strip()


def _extract_career_prospects(text: str, max_roles: int = 6) -> list:
    """Return job-role / salary lines. Falls back to short title-like lines."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    salary_lines = [l for l in lines if "£" in l or "salary" in l.lower()]
    if salary_lines:
        return salary_lines[:max_roles]
    role_lines = [l for l in lines if len(l) < 100 and not l.endswith(".")]
    return role_lines[:max_roles]


# ── Academic progression extraction ─────────────────────────

_PATHWAY_KEYWORDS = [
    "level", "step", "degree", "bachelor", "master", "diploma",
    "certificate", "hnd", "hnc", "foundation", "top-up", "top up",
    "pgce", "postgraduate", "undergraduate", "university",
    "ba ", "bsc", "mba", "msc", "acca", "cima",
]


def _extract_pathway_lines(text: str) -> list:
    """Return only the meaningful progression pathway lines."""
    all_lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    pathway_lines = []
    for line in all_lines:
        low = line.lower()
        if any(kw in low for kw in _PATHWAY_KEYWORDS):
            pathway_lines.append(line)
    return pathway_lines if pathway_lines else all_lines


# ═══════════════════════════════════════════════════════════
# CourseLoader
# ═══════════════════════════════════════════════════════════

class CourseLoader:
    def __init__(self, filepath: str = "courses.xlsx"):
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Course data file not found: {filepath}")

        self.df = pd.read_excel(filepath)
        self.df.columns = [c.strip().rstrip(":").strip() for c in self.df.columns]
        self.df.columns = [
            "Number of Credits" if c.lower() == "number of credits" else c
            for c in self.df.columns
        ]
        for col in self.df.columns:
            self.df[col] = self.df[col].fillna("").astype(str).str.strip()
        self.df = self.df[self.df["Course Name"].str.strip() != ""].reset_index(drop=True)

        self._search_text = []
        for _, row in self.df.iterrows():
            blob = " ".join([
                row.get("Course Name", "") * 3,
                row.get("Course Overview", ""),
                row.get("Who is This Certification For?", ""),
                row.get("Career Progression", ""),
                row.get("Learning Outcomes", ""),
                row.get("Qualification Level", ""),
                row.get("Course Qualification Type", ""),
                row.get("Guided Learning Hours", ""),
                row.get("Total Qualification Time", ""),
                row.get("Number of Credits", ""),
                row.get("Academic Progression", ""),
                row.get("Entry Requirements", ""),
                row.get("Awarded by", ""),
                row.get("Method of Assessment", ""),
                row.get("Certification", ""),
                row.get("Regulated by", ""),
                row.get("Qualification Number", ""),
            ]).lower()
            self._search_text.append(blob)

        print(f"Loaded {len(self.df)} courses from {filepath}")

    def search(self, query: str, top_n: int = 6) -> list:
        terms = _expand_query(query)
        if not terms:
            return []
        scored = []
        for idx, blob in enumerate(self._search_text):
            blob_words = _tokenize(blob)
            score = 0
            for term in terms:
                term_words = _tokenize(term)
                if term_words.issubset(blob_words):
                    name_lower = self.df.iloc[idx]["Course Name"].lower()
                    if all(w in _tokenize(name_lower) for w in term_words):
                        score += 4
                    else:
                        score += 1
                elif term.lower() in blob:
                    score += 2
            if score > 0:
                scored.append((score, idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self.df.iloc[idx].to_dict() for _, idx in scored[:top_n]]

    # ─────────────────────────────────────────────────────────
    # Search card (max 3 courses) — used in SEARCH MODE
    # ─────────────────────────────────────────────────────────

    def format_course_for_bot(self, course: dict) -> str:
        def val(key):
            return course.get(key, "").strip()

        lines = []

        lines.append(f"COURSE: {val('Course Name')}")
        lines.append(f"URL: {val('Course URL')}")

        facts = []
        if val("Qualification Level"):       facts.append(f"Level: {val('Qualification Level')}")
        if val("Course Qualification Type"): facts.append(f"Type: {val('Course Qualification Type')}")
        if val("Awarded by"):                facts.append(f"Awarded by: {val('Awarded by')}")
        if val("Regulated by"):
            reg = val("Regulated by").split("\n")[0].strip()
            if reg: facts.append(f"Regulated: {reg}")
        if facts:
            lines.append(" | ".join(facts))

        dur = []
        if val("Standard Duration"):         dur.append(f"Standard: {val('Standard Duration')}")
        if val("Fast Track Duration"):       dur.append(f"Fast Track: {val('Fast Track Duration')}")
        if val("Access Duration"):           dur.append(f"Access: {val('Access Duration')}")
        if val("Guided Learning Hours"):     dur.append(f"GLH: {val('Guided Learning Hours')}")
        if val("Total Qualification Time"):  dur.append(f"TQT: {val('Total Qualification Time')}")
        if val("Number of Credits"):         dur.append(f"Credits: {val('Number of Credits')}")
        if dur:
            lines.append("Duration & Hours: " + " | ".join(dur))

        if val("Course Overview"):
            lines.append(f"Overview: {_first_sentences(val('Course Overview'), 2)}")

        if val("Learning Outcomes"):
            lo_lines = [l.strip() for l in val("Learning Outcomes").splitlines() if l.strip()]
            if lo_lines:
                lines.append("What you will learn:")
                lines.append(_bullet(val("Learning Outcomes"), max_items=4))

        if val("Who is This Certification For?"):
            who_lines = [l.strip() for l in val("Who is This Certification For?").splitlines() if l.strip()]
            if len(who_lines) > 1:
                lines.append("Who it is for:")
                lines.append(_bullet(val("Who is This Certification For?"), max_items=4))
            else:
                lines.append(f"Who it is for: {who_lines[0] if who_lines else ''}")

        if val("Entry Requirements"):
            er_lines = [l.strip() for l in val("Entry Requirements").splitlines() if l.strip()]
            if len(er_lines) > 1:
                lines.append("Entry Requirements:")
                lines.append(_bullet(val("Entry Requirements")))
            else:
                lines.append(f"Entry Requirements: {er_lines[0] if er_lines else ''}")

        if val("Method of Assessment"):
            assess_text = val("Method of Assessment")
            assess_summary = _first_sentences(assess_text, 2)
            lines.append(f"Assessment: {assess_summary}")

        if val("Career Progression"):
            career_lines = [l.strip() for l in val("Career Progression").splitlines() if l.strip()]
            salary_lines = [l for l in career_lines if "£" in l or "salary" in l.lower()]
            intro_lines = [l for l in career_lines if "£" not in l and len(l) < 120][:2]
            if salary_lines:
                lines.append("Career Progression:")
                if intro_lines:
                    lines.append(_bullet("\n".join(intro_lines)))
                lines.append(_bullet("\n".join(salary_lines[:5])))
            elif career_lines:
                lines.append(f"Career Progression: {_first_sentences(val('Career Progression'), 2)}")

        if val("Academic Progression"):
            acad_lines = [l.strip() for l in val("Academic Progression").splitlines() if l.strip()]
            step_lines = [l for l in acad_lines if l.lower().startswith("step")]
            intro = _first_sentences(val("Academic Progression"), 1)
            if step_lines:
                lines.append("Academic Progression:")
                lines.append(f"→ {intro}")
                lines.append(_bullet("\n".join(step_lines[:3])))
            else:
                lines.append(f"Academic Progression: {intro}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────
    # Full details — used in FULL DETAILS MODE
    # ⚠️  Heading names MUST match test_chat.html formatBotText
    # ─────────────────────────────────────────────────────────

    def format_full_course(self, course: dict) -> str:
        def val(key):
            return course.get(key, "").strip()

        lines = []

        # ── Header ──────────────────────────────────────────
        lines.append(f"📘 {val('Course Name')}")
        lines.append(f"🔗 {val('Course URL')}")
        lines.append("")

        # ── Key facts ───────────────────────────────────────
        facts = []
        if val("Qualification Level"):  facts.append(val("Qualification Level"))
        if val("Awarded by"):           facts.append(f"Awarded by: {val('Awarded by')}")
        if val("Regulated by"):
            reg = val("Regulated by").split("\n")[0].strip()
            if reg: facts.append(reg)
        if facts:
            lines.append("  •  ".join(facts))
        if val("Qualification Number"):
            lines.append(f"Qualification No: {val('Qualification Number')}")
        lines.append("")

        # ── Duration & Hours ────────────────────────────────
        lines.append("Duration & Hours:")
        if val("Standard Duration"):        lines.append(f"→ Standard: {val('Standard Duration')}")
        if val("Fast Track Duration"):      lines.append(f"→ Fast Track: {val('Fast Track Duration')}")
        if val("Access Duration"):          lines.append(f"→ Access Period: {val('Access Duration')}")
        if val("Guided Learning Hours"):    lines.append(f"→ Guided Learning Hours: {val('Guided Learning Hours')}")
        if val("Total Qualification Time"): lines.append(f"→ Total Qualification Time: {val('Total Qualification Time')}")
        if val("Number of Credits"):        lines.append(f"→ Credits: {val('Number of Credits')}")
        lines.append("")

        # ── Overview ────────────────────────────────────────
        if val("Course Overview"):
            lines.append("Overview:")
            sentences = val("Course Overview").replace("\n", " ").split(". ")
            summary = ". ".join(sentences[:2]).strip()
            if not summary.endswith("."):
                summary += "."
            lines.append(summary)
            lines.append(f"👉 Full details: {val('Course URL')}")
            lines.append("")

        # ── Learning Outcomes ───────────────────────────────
        if val("Learning Outcomes"):
            lines.append("What you will learn:")
            lines.append(_bullet(val("Learning Outcomes")))
            lines.append("")

        # ── Who it is for ───────────────────────────────────
        if val("Who is This Certification For?"):
            lines.append("Who it is for:")
            lines.append(_bullet(val("Who is This Certification For?")))
            lines.append("")

        # ── Entry Requirements ──────────────────────────────
        if val("Entry Requirements"):
            lines.append("Entry Requirements:")
            lines.append(_bullet(val("Entry Requirements")))
            lines.append("")

        # ── Method of Assessment (concise — main methods only) ──
        if val("Method of Assessment"):
            lines.append("Method of Assessment:")
            methods = _extract_assessment_methods(val("Method of Assessment"))
            lines.append("\n".join(f"→ {m}" for m in methods))
            assess_lower = val("Method of Assessment").lower()
            if "no exam" in assess_lower or "no formal exam" in assess_lower:
                lines.append("→ No formal examinations required")
            lines.append("")

        # ── Certification ───────────────────────────────────
        if val("Certification"):
            lines.append("Certification:")
            lines.append(_bullet(val("Certification")))
            lines.append("")

        # ── Career Progression (intro + prospects) ──────────
        if val("Career Progression"):
            lines.append("Career Progression:")

            intro = _extract_career_intro(val("Career Progression"), max_sentences=3)
            if intro:
                lines.append(intro)
                lines.append("")

            prospects = _extract_career_prospects(val("Career Progression"), max_roles=6)
            if prospects:
                lines.append("Career Prospects:")
                lines.append("\n".join(f"→ {p}" for p in prospects))
            lines.append("")

        # ── Academic Progression (clean pathway list) ───────
        if val("Academic Progression"):
            lines.append("Possible Academic Progression Pathway:")
            pathway_lines = _extract_pathway_lines(val("Academic Progression"))
            lines.append("\n".join(f"→ {p}" for p in pathway_lines))
            lines.append("")

        return "\n".join(lines)

    def get_context_for_query(self, query: str) -> str:
        results = self.search(query)
        if not results:
            return "No matching courses found. Suggest the learner visits the website or contacts admissions."
        return "\n\n".join(self.format_course_for_bot(c) for c in results)

    def get_full_details_for_query(self, query: str) -> str:
        results = self.search(query, top_n=1)
        if not results:
            return "No matching course found. Suggest the learner visits the website or contacts admissions."
        return self.format_full_course(results[0])
