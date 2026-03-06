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
    """Convert newline-separated text into → bullet lines, optional max items."""
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

    def format_course_for_bot(self, course: dict) -> str:
        """
        Rich summary card — used for search results (max 3 courses).
        Includes all important fields with bullet points where helpful.
        """
        def val(key):
            return course.get(key, "").strip()

        lines = []

        # ── Header ──────────────────────────────────────────
        lines.append(f"COURSE: {val('Course Name')}")
        lines.append(f"URL: {val('Course URL')}")

        # ── Key facts ───────────────────────────────────────
        facts = []
        if val("Qualification Level"):       facts.append(f"Level: {val('Qualification Level')}")
        if val("Course Qualification Type"): facts.append(f"Type: {val('Course Qualification Type')}")
        if val("Awarded by"):                facts.append(f"Awarded by: {val('Awarded by')}")
        if val("Regulated by"):
            reg = val("Regulated by").split("\n")[0].strip()
            if reg: facts.append(f"Regulated: {reg}")
        if facts:
            lines.append(" | ".join(facts))

        # ── Duration & hours ─────────────────────────────────
        dur = []
        if val("Standard Duration"):         dur.append(f"Standard: {val('Standard Duration')}")
        if val("Fast Track Duration"):       dur.append(f"Fast Track: {val('Fast Track Duration')}")
        if val("Access Duration"):           dur.append(f"Access: {val('Access Duration')}")
        if val("Guided Learning Hours"):     dur.append(f"GLH: {val('Guided Learning Hours')}")
        if val("Total Qualification Time"):  dur.append(f"TQT: {val('Total Qualification Time')}")
        if val("Number of Credits"):         dur.append(f"Credits: {val('Number of Credits')}")
        if dur:
            lines.append("Duration & Hours: " + " | ".join(dur))

        # ── Overview ─────────────────────────────────────────
        if val("Course Overview"):
            lines.append(f"Overview: {_first_sentences(val('Course Overview'), 2)}")

        # ── Learning Outcomes (bullet list, max 4) ───────────
        if val("Learning Outcomes"):
            lo_lines = [l.strip() for l in val("Learning Outcomes").splitlines() if l.strip()]
            if lo_lines:
                lines.append("What you will learn:")
                lines.append(_bullet(val("Learning Outcomes"), max_items=4))

        # ── Who it is for ────────────────────────────────────
        if val("Who is This Certification For?"):
            who_lines = [l.strip() for l in val("Who is This Certification For?").splitlines() if l.strip()]
            if len(who_lines) > 1:
                lines.append("Who it is for:")
                lines.append(_bullet(val("Who is This Certification For?"), max_items=4))
            else:
                lines.append(f"Who it is for: {who_lines[0] if who_lines else ''}")

        # ── Entry Requirements (bullet list) ─────────────────
        if val("Entry Requirements"):
            er_lines = [l.strip() for l in val("Entry Requirements").splitlines() if l.strip()]
            if len(er_lines) > 1:
                lines.append("Entry Requirements:")
                lines.append(_bullet(val("Entry Requirements")))
            else:
                lines.append(f"Entry Requirements: {er_lines[0] if er_lines else ''}")

        # ── Method of Assessment ──────────────────────────────
        if val("Method of Assessment"):
            # First sentence summary + note about no exams if relevant
            assess_text = val("Method of Assessment")
            assess_summary = _first_sentences(assess_text, 2)
            lines.append(f"Assessment: {assess_summary}")

        # ── Career Progression (bullet list, keep important detail) ──
        if val("Career Progression"):
            career_lines = [l.strip() for l in val("Career Progression").splitlines() if l.strip()]
            # Filter to lines with salary info or short job-like lines
            salary_lines = [l for l in career_lines if "£" in l or "salary" in l.lower()]
            intro_lines = [l for l in career_lines if "£" not in l and len(l) < 120][:2]
            if salary_lines:
                lines.append("Career Progression:")
                if intro_lines:
                    lines.append(_bullet("\n".join(intro_lines)))
                lines.append(_bullet("\n".join(salary_lines[:5])))
            elif career_lines:
                lines.append(f"Career Progression: {_first_sentences(val('Career Progression'), 2)}")

        # ── Academic Progression ──────────────────────────────
        if val("Academic Progression"):
            acad_lines = [l.strip() for l in val("Academic Progression").splitlines() if l.strip()]
            # Show first 2 sentences + step lines if they exist
            step_lines = [l for l in acad_lines if l.lower().startswith("step")]
            intro = _first_sentences(val("Academic Progression"), 1)
            if step_lines:
                lines.append("Academic Progression:")
                lines.append(f"→ {intro}")
                lines.append(_bullet("\n".join(step_lines[:3])))
            else:
                lines.append(f"Academic Progression: {intro}")

        return "\n".join(lines)

    def format_full_course(self, course: dict) -> str:
        """Full details — Option 3 Clean Minimal, easy to read on any device."""
        def val(key):
            return course.get(key, "").strip()

        def bullet(text, max_items=99):
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if not lines:
                return text.strip()
            if len(lines) == 1:
                return lines[0]
            return "\n".join(f"→ {l}" for l in lines[:max_items])

        def first_sentences(text, n=2):
            text = text.replace("\n", " ").strip()
            parts = text.split(". ")
            result = ". ".join(parts[:n]).strip()
            if result and not result.endswith("."): result += "."
            return result

        lines = []

        # ── Header ──────────────────────────────────────────
        lines.append(f"📘 {val('Course Name')}")
        lines.append("──────────────────────────")

        facts = []
        if val("Awarded by"):           facts.append(val("Awarded by"))
        if val("Regulated by"):
            reg = val("Regulated by").split("\n")[0].strip()
            if reg: facts.append(reg)
        if val("Number of Credits"):    facts.append(val("Number of Credits"))
        if val("Qualification Number"): facts.append(f"Qual: {val('Qualification Number')}")
        if facts:
            lines.append("  |  ".join(facts))
        lines.append("")

        # ── How Long ─────────────────────────────────────────
        lines.append("HOW LONG")
        dur = []
        if val("Standard Duration"):        dur.append(f"Standard {val('Standard Duration')}")
        if val("Fast Track Duration"):      dur.append(f"Fast Track {val('Fast Track Duration')}")
        if dur:
            lines.append(f"→ {'  •  '.join(dur)}")
        hc = []
        if val("Guided Learning Hours"):    hc.append(f"{val('Guided Learning Hours')} learning hours")
        if val("Total Qualification Time"): hc.append(f"{val('Total Qualification Time')} total study time")
        if val("Access Duration"):          hc.append(f"Access period: {val('Access Duration')}")
        if hc:
            lines.append(f"→ {'  •  '.join(hc)}")
        lines.append("")

        # ── About This Course ─────────────────────────────────
        if val("Course Overview"):
            lines.append("ABOUT THIS COURSE")
            lines.append(first_sentences(val("Course Overview"), 3))
            lines.append(f"👉 {val('Course URL')}")
            lines.append("")

        # ── You Will Learn To ─────────────────────────────────
        if val("Learning Outcomes"):
            lines.append("YOU WILL LEARN TO")
            lines.append(bullet(val("Learning Outcomes")))
            lines.append("")

        # ── Perfect For ───────────────────────────────────────
        if val("Who is This Certification For?"):
            lines.append("PERFECT FOR")
            lines.append(bullet(val("Who is This Certification For?")))
            lines.append("")

        # ── To Enrol You Need ─────────────────────────────────
        if val("Entry Requirements"):
            lines.append("TO ENROL YOU NEED")
            lines.append(bullet(val("Entry Requirements")))
            lines.append("")

        # ── How You Are Assessed ──────────────────────────────
        if val("Method of Assessment"):
            lines.append("HOW YOU ARE ASSESSED")
            lines.append(bullet(val("Method of Assessment")))
            lines.append("")

        # ── Certification ─────────────────────────────────────
        if val("Certification"):
            lines.append("YOUR CERTIFICATE")
            lines.append(bullet(val("Certification")))
            lines.append("")

        # ── Career Paths & Salaries ───────────────────────────
        if val("Career Progression"):
            lines.append("CAREER PATHS & SALARIES")
            career_lines = [l.strip() for l in val("Career Progression").splitlines() if l.strip()]
            salary_lines = [l for l in career_lines if "£" in l]
            intro_lines  = [l for l in career_lines if "£" not in l and len(l) < 120]
            if intro_lines:
                lines.append(f"→ {intro_lines[0]}")
            if salary_lines:
                # Align salary lines nicely
                for sl in salary_lines[:6]:
                    if "–" in sl or "-" in sl:
                        sep = "–" if "–" in sl else "-"
                        parts = sl.split(sep, 1)
                        job = parts[0].strip()
                        sal = parts[1].strip() if len(parts) > 1 else ""
                        dots = "." * max(1, 28 - len(job))
                        lines.append(f"→ {job} {dots} {sal}")
                    else:
                        lines.append(f"→ {sl}")
            elif career_lines:
                lines.append(bullet(val("Career Progression"), max_items=6))
            lines.append("")

        # ── Where This Leads ──────────────────────────────────
        if val("Academic Progression"):
            lines.append("WHERE THIS LEADS")
            acad_lines = [l.strip() for l in val("Academic Progression").splitlines() if l.strip()]
            step_lines  = [l for l in acad_lines if l.lower().startswith("step")]
            qual_lines  = [l for l in acad_lines if not l.lower().startswith("step")
                           and "£" not in l and len(l) < 100 and len(l) > 5][:3]
            if step_lines:
                lines.append(bullet("\n".join(step_lines[:5])))
            elif qual_lines:
                lines.append(bullet("\n".join(qual_lines)))
            else:
                lines.append(bullet(val("Academic Progression"), max_items=4))
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
