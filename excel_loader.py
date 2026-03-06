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


def _bullet_lines(text: str) -> str:
    """Convert newline-separated text into bullet points."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) <= 1:
        return text.strip()
    return "\n".join(f"• {l}" for l in lines)


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
        """Brief summary — used for general search results."""
        def val(key):
            return course.get(key, "").strip()

        lines = []
        lines.append(f"COURSE: {val('Course Name')}")
        lines.append(f"URL: {val('Course URL')}")
        lines.append(f"Level: {val('Qualification Level')} | Type: {val('Course Qualification Type')} | Awarded by: {val('Awarded by')}")

        dur_parts = []
        if val("Standard Duration"):    dur_parts.append(f"Standard: {val('Standard Duration')}")
        if val("Fast Track Duration"):  dur_parts.append(f"Fast Track: {val('Fast Track Duration')}")
        if val("Access Duration"):      dur_parts.append(f"Access Period: {val('Access Duration')}")
        if dur_parts:
            lines.append(f"Duration: {' | '.join(dur_parts)}")

        hc_parts = []
        if val("Guided Learning Hours"):    hc_parts.append(f"GLH: {val('Guided Learning Hours')}")
        if val("Total Qualification Time"): hc_parts.append(f"TQT: {val('Total Qualification Time')}")
        if val("Number of Credits"):        hc_parts.append(f"Credits: {val('Number of Credits')}")
        if hc_parts:
            lines.append(f"{' | '.join(hc_parts)}")

        if val("Course Overview"):
            ov = val("Course Overview")
            lines.append(f"Overview: {ov[:400].rsplit(' ', 1)[0]}..." if len(ov) > 400 else f"Overview: {ov}")

        if val("Who is This Certification For?"):
            t = val("Who is This Certification For?")
            lines.append(f"Best for: {t[:200].rsplit(' ', 1)[0]}..." if len(t) > 200 else f"Best for: {t}")

        if val("Entry Requirements"):
            r = val("Entry Requirements")
            lines.append(f"Entry Requirements: {r[:200].rsplit(' ', 1)[0]}..." if len(r) > 200 else f"Entry Requirements: {r}")

        if val("Method of Assessment"):
            m = val("Method of Assessment")
            lines.append(f"Assessment: {m[:200].rsplit(' ', 1)[0]}..." if len(m) > 200 else f"Assessment: {m}")

        if val("Career Progression"):
            c = val("Career Progression")
            lines.append(f"Career Paths: {c[:250].rsplit(' ', 1)[0]}..." if len(c) > 250 else f"Career Paths: {c}")

        if val("Academic Progression"):
            p = val("Academic Progression")
            lines.append(f"Academic Progression: {p[:200].rsplit(' ', 1)[0]}..." if len(p) > 200 else f"Academic Progression: {p}")

        return "\n".join(lines)

    def format_full_course(self, course: dict) -> str:
        """Full details — Option B Minimal & Modern with arrow bullets."""
        def val(key):
            return course.get(key, "").strip()

        def arrow_lines(text):
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if len(lines) <= 1:
                return text.strip()
            return "\n".join(f"→ {l}" for l in lines)

        lines = []

        # Header
        lines.append(f"📘 {val('Course Name')}")
        lines.append(f"🔗 {val('Course URL')}")
        lines.append("")

        # Key facts
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

        # Duration & hours
        lines.append("⏱️ Duration & Hours")
        lines.append("──────────────────────────")
        if val("Standard Duration"):        lines.append(f"  Standard:              {val('Standard Duration')}")
        if val("Fast Track Duration"):      lines.append(f"  Fast Track:            {val('Fast Track Duration')}")
        if val("Access Duration"):          lines.append(f"  Access Period:         {val('Access Duration')}")
        if val("Guided Learning Hours"):    lines.append(f"  Guided Learning Hours: {val('Guided Learning Hours')}")
        if val("Total Qualification Time"): lines.append(f"  Total Qual Time:       {val('Total Qualification Time')}")
        if val("Number of Credits"):        lines.append(f"  Credits:               {val('Number of Credits')}")
        lines.append("")

        # Overview — 2 sentence summary + link
        if val("Course Overview"):
            lines.append("Overview")
            lines.append("──────────────────────────")
            sentences = val("Course Overview").replace("\n", " ").split(". ")
            summary = ". ".join(sentences[:2]).strip()
            if not summary.endswith("."): summary += "."
            lines.append(summary)
            lines.append(f"👉 Full details: {val('Course URL')}")
            lines.append("")

        if val("Learning Outcomes"):
            lines.append("What you will learn")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Learning Outcomes")))
            lines.append("")

        if val("Who is This Certification For?"):
            lines.append("Who it is for")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Who is This Certification For?")))
            lines.append("")

        if val("Entry Requirements"):
            lines.append("Entry Requirements")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Entry Requirements")))
            lines.append("")

        if val("Method of Assessment"):
            lines.append("Method of Assessment")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Method of Assessment")))
            lines.append("")

        if val("Certification"):
            lines.append("Certification")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Certification")))
            lines.append("")

        if val("Career Progression"):
            lines.append("Career Progression")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Career Progression")))
            lines.append("")

        if val("Academic Progression"):
            lines.append("Academic Progression")
            lines.append("──────────────────────────")
            lines.append(arrow_lines(val("Academic Progression")))
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
