"""Extract text from PDF/DOCX resumes and run skill NER over it (Module A)."""

import io
import re
from collections import Counter
from functools import lru_cache

from app.nlp.taxonomy import CASE_SENSITIVE, SKILLS

MIN_TEXT_CHARS = 150  # below this the file is probably scanned/image-only -> manual review
MAX_FILE_BYTES = 5 * 1024 * 1024

_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+\w+){0,3}\s+experience", re.I)
_GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9-]{1,39})(?![A-Za-z0-9-])", re.I)
_SENIOR_RE = re.compile(r"\b(senior|lead|principal|staff engineer|architect)\b", re.I)
_JUNIOR_RE = re.compile(r"\b(intern|internship|student|undergraduate|b\.?\s?e\.?|b\.?tech|fresher)\b", re.I)


class UnreadableResume(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise UnreadableResume("file larger than 5 MB")
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            import pdfplumber

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages[:10])
        elif name.endswith(".docx"):
            import docx

            doc = docx.Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        elif name.endswith(".txt"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise UnreadableResume("unsupported format (use PDF, DOCX or TXT)")
    except UnreadableResume:
        raise
    except Exception as exc:  # corrupt files raise many different library errors
        raise UnreadableResume(f"could not read file: {type(exc).__name__}") from exc
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise UnreadableResume("no extractable text (scanned or image-only document?)")
    return text


@lru_cache
def _nlp():
    import spacy

    nlp = spacy.blank("en")
    # Two rulers: most aliases match case-insensitively, a few only with exact casing.
    lower = nlp.add_pipe("entity_ruler", name="skills_lower", config={"phrase_matcher_attr": "LOWER"})
    exact = nlp.add_pipe("entity_ruler", name="skills_exact", config={"phrase_matcher_attr": "ORTH", "overwrite_ents": False})
    lower_patterns, exact_patterns = [], []
    for canon, (_cat, aliases) in SKILLS.items():
        for alias in {canon, *aliases}:
            if alias in CASE_SENSITIVE:
                exact_patterns.append({"label": "SKILL", "pattern": alias, "id": canon})
            else:
                lower_patterns.append({"label": "SKILL", "pattern": alias.lower(), "id": canon})
    lower.add_patterns(lower_patterns)
    exact.add_patterns(exact_patterns)
    return nlp


def extract_skills(text: str) -> list[dict]:
    doc = _nlp()(text[:100_000])
    counts = Counter(ent.ent_id_ for ent in doc.ents if ent.label_ == "SKILL")
    return [
        {"name": name, "category": SKILLS[name][0], "mentions": n, "source": "resume"}
        for name, n in counts.most_common()
    ]


def estimate_experience(text: str) -> tuple[float | None, str]:
    years = [float(m.group(1)) for m in _YEARS_RE.finditer(text)]
    best = max((y for y in years if y <= 40), default=None)
    if best is not None:
        level = "advanced" if best >= 4 else "intermediate" if best >= 1.5 else "beginner"
    elif _SENIOR_RE.search(text):
        level = "advanced"
    elif _JUNIOR_RE.search(text):
        level = "beginner"
    else:
        level = "intermediate"
    return best, level


def parse_resume(filename: str, data: bytes) -> dict:
    text = extract_text(filename, data)
    years, level = estimate_experience(text)
    gh = _GITHUB_RE.search(text)
    return {
        "skills": extract_skills(text),
        "experience_years": years,
        "experience_level": level,
        "github_url": f"https://github.com/{gh.group(1)}" if gh else None,
        "text_chars": len(text),
    }
