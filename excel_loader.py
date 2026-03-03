import re
import pandas as pd
from pathlib import Path


# Synonyms map — expands short or common terms into better search keywords
SYNONYMS = {
    "it":           ["computing", "digital", "technology", "information"],
    "tech":         ["computing", "digital", "technology", "information"],
    "computer":     ["computing", "digital", "technology"],
    "computers":    ["computing", "digital", "technology"],
    "coding":       ["programming", "computing", "software", "developer"],
    "code":         ["programming", "computing", "software"],
    "web":          ["web development", "digital", "computing"],
    "cyber":        ["cyber security", "computing", "digital"],
    "security":     ["cyber security", "computing"],
    "data":         ["data analyst", "computing", "digital"],
    "software":     ["software developer", "computing", "programming"],
    "finance":      ["accounting", "finance"],
    "money":        ["accounting", "finance"],
    "hr":           ["human resources", "business"],
    "health":       ["health", "social care", "healthcare"],
    "care":         ["social care", "health", "adult care"],
    "nurse":        ["health", "social care", "nursing"],
    "teach":        ["teaching", "education", "teacher"],
    "teacher":      ["teaching", "education", "foundations of teaching"],
    "law":          ["law", "legal"],
    "legal":        ["law", "legal"],
    "management":   ["management", "business", "leadership"],
    "marketing":    ["marketing", "business", "digital"],
    "project":      ["project management", "business", "management"],
    "pm":           ["project management"],
    "leadership":   ["leadership", "management", "business"],
    "psychology":   ["psychology", "counselling", "mental health"],
    "mental":       ["mental health", "psychology", "counselling"],
    "maths":        ["mathematics", "maths", "functional skills"],
    "math":         ["mathematics", "maths", "functional skills"],
    "english":      ["english", "functional skills", "communication"],
    "sport":        ["sport", "physical education", "fitness"],
    "fitness":      ["fitness", "sport", "personal training"],
    "childcare":    ["childcare", "child", "early years"],
    "early years":  ["early years", "childcare"],
    "logistics":    ["logistics", "supply chain", "operations"],
    "supply chain": ["supply chain", "logistics", "operations"],
    "hospitality":  ["hospitality", "hotel", "tourism"],
    "tourism":      ["tourism", "hospitality", "travel"],
}


def _tokenize(text: str) -> set:
    """Split text into lowercase words."""
    return set(re.findall(r"\b\w+\b", text.lower()))


def _expand_query(query: str) -> list[str]:
    """
    Return a flat list of search terms expanded via synonyms.
    Handles short terms like 'IT' by not filtering by length.
    """
    terms = []
    query_lower = query.lower().strip()

    # Check for multi-word synonym keys first
    for key, expansions in SYNONYMS.items():
        if key in query_lower:
            terms.extend(expansions)

    # Add original individual words (no length filter — 'it' must be included)
    for word in re.findall(r"\b\w+\b", query_lower):
        if word not in ("the", "a", "an", "is", "are", "do", "does", "can", "any", "for", "in", "of", "and", "or", "to"):
            terms.append(word)

    return list(set(terms))  # deduplicate


class CourseLoader:
    def __init__(self, filepath: str = "courses.xlsx"):
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Course data file not found: {filepath}")

        self.df = pd.read_excel(filepath)
        self.df.columns = [c.strip().rstrip(":").strip() for c in self.df.columns]

        for col in self.df.columns:
            self.df[col] = self.df[col].fillna("").astype(str).str.strip()

        self.df = self.df[self.df["Course Name"].str.strip() != ""].reset_index(drop=True)

        # Pre-build a searchable text blob per course for fast lookup
        self._search_text = []
        for _, row in self.df.iterrows():
            blob = " ".join([
                row.get("Course Name", "") * 3,   # weight name more
                row.get("Course Overview", ""),
                row.get("Who is This Certification For?", ""),
                row.get("Career Progression", ""),
                row.get("Learning Outcomes", ""),
                row.get("Qualification Level", ""),
                row.get("Course Qualification Type", ""),
            ]).lower()
            self._search_text.append(blob)

        print(f"✅ Loaded {len(self.df)} courses from {filepath}")

    def search(self, query: str, top_n: int = 6) -> list[dict]:
        """Score every course against expanded query terms and return top matches."""
        terms = _expand_query(query)
        if not terms:
            return []

        scored = []
        for idx, blob in enumerate(self._search_text):
            blob_words = _tokenize(blob)
            score = 0
            for term in terms:
                term_words = _tokenize(term)
                # Exact word match in blob
                if term_words.issubset(blob_words):
                    # Name matches score higher
                    name_lower = self.df.iloc[idx]["Course Name"].lower()
                    if all(w in _tokenize(name_lower) for w in term_words):
                        score += 4
                    else:
                        score += 1
                # Partial substring match for multi-word terms
                elif term.lower() in blob:
                    score += 2

            if score > 0:
                scored.append((score, idx))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self.df.iloc[idx].to_dict() for _, idx in scored[:top_n]]

    def format_course_for_bot(self, course: dict) -> str:
        """Build a concise informative text block for one course."""
        def val(key):
            return course.get(key, "").strip()

        lines = []
        lines.append(f"📘 COURSE: {val('Course Name')}")
        lines.append(f"   URL: {val('Course URL')}")
        lines.append(f"   Level: {val('Qualification Level')} | Type: {val('Course Qualification Type')} | Awarded by: {val('Awarded by')}")

        parts = []
        if val("Standard Duration"):   parts.append(f"Standard: {val('Standard Duration')}")
        if val("Fast Track Duration"):  parts.append(f"Fast Track: {val('Fast Track Duration')}")
        if val("Access Duration"):      parts.append(f"Access Period: {val('Access Duration')}")
        if parts:
            lines.append(f"   Duration — {' | '.join(parts)}")

        if val("Course Overview"):
            ov = val("Course Overview")
            lines.append(f"   Overview: {ov[:400].rsplit(' ', 1)[0]}..." if len(ov) > 400 else f"   Overview: {ov}")

        if val("Who is This Certification For?"):
            t = val("Who is This Certification For?")
            lines.append(f"   Best for: {t[:200].rsplit(' ', 1)[0]}..." if len(t) > 200 else f"   Best for: {t}")

        if val("Entry Requirements"):
            r = val("Entry Requirements")
            lines.append(f"   Entry Requirements: {r[:200].rsplit(' ', 1)[0]}..." if len(r) > 200 else f"   Entry Requirements: {r}")

        if val("Career Progression"):
            c = val("Career Progression")
            lines.append(f"   Career Paths: {c[:250].rsplit(' ', 1)[0]}..." if len(c) > 250 else f"   Career Paths: {c}")

        if val("Academic Progression"):
            p = val("Academic Progression")
            lines.append(f"   Academic Progression: {p[:200].rsplit(' ', 1)[0]}..." if len(p) > 200 else f"   Academic Progression: {p}")

        return "\n".join(lines)

    def get_context_for_query(self, query: str) -> str:
        """Return formatted course context for the top matching courses."""
        results = self.search(query)
        if not results:
            return "No matching courses found. Suggest the learner visits the website or contacts admissions."
        return "\n\n".join(self.format_course_for_bot(c) for c in results)