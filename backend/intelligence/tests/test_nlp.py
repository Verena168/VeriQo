from app.nlp.resume_parser import estimate_experience, extract_skills, parse_resume
from app.nlp.skill_matcher import match
from app.nlp.taxonomy import canonicalize
from app.nlp.team_builder import form_teams

RESUME = """Priya Sharma — B.Tech Computer Engineering student
github.com/priya-dev
Skills: Python, React.js, Node.js, PostgreSQL, Docker, scikit-learn, TensorFlow
Built a REST API with FastAPI and deployed it on AWS. 2 years of experience in web development.
I like to Go hiking. Interned at a startup doing machine learning and NLP research for the rest of the summer.
"""


def names(skills):
    return {s["name"] for s in skills}


def test_skill_ner_finds_aliases_and_avoids_common_words():
    found = names(extract_skills(RESUME))
    assert {"Python", "React", "Node.js", "PostgreSQL", "Docker", "scikit-learn", "TensorFlow", "FastAPI", "AWS",
            "Machine Learning", "Natural Language Processing"} <= found
    assert "Go" in found  # capitalised "Go" in "Go hiking" is a known false positive of case rules
    assert "REST APIs" in found  # from "REST API", while "the rest of" must not match
    found_lower = names(extract_skills("we will go home and rest; spring is nice"))
    assert found_lower == set()


def test_experience_and_github_extraction():
    years, level = estimate_experience(RESUME)
    assert years == 2.0 and level == "intermediate"
    parsed = parse_resume("cv.txt", RESUME.encode())
    assert parsed["github_url"] == "https://github.com/priya-dev"


def test_canonicalize():
    assert canonicalize("reactjs") == "React"
    assert canonicalize("Jupyter Notebook") == "Python"
    assert canonicalize("unknown-thing") is None


def test_match_exact_category_and_weights():
    reqs = [{"skill": "Python", "weight": 3}, {"skill": "Machine Learning", "weight": 2}, {"skill": "Kubernetes", "weight": 1}]
    r = match(["python", "PyTorch"], reqs, threshold=0.99)  # threshold so high only exact/category apply
    by = {b["skill"]: b for b in r["breakdown"]}
    assert by["Python"]["matched_by"] == "exact"
    assert by["Machine Learning"]["matched_by"] == "category" and by["Machine Learning"]["evidence"] == "PyTorch"
    assert by["Kubernetes"]["score"] == 0
    assert r["score"] == round(100 * (3 * 1 + 2 * 0.5) / 6, 1)


def test_team_builder_balances_and_respects_size():
    reqs = [{"skill": "React", "weight": 2}, {"skill": "Python", "weight": 2}, {"skill": "Docker", "weight": 1}]
    people = [
        {"id": "a", "skills": ["React"], "score": 90}, {"id": "b", "skills": ["React"], "score": 85},
        {"id": "c", "skills": ["Python"], "score": 80}, {"id": "d", "skills": ["Python"], "score": 70},
        {"id": "e", "skills": ["Docker"], "score": 60}, {"id": "f", "skills": ["Docker"], "score": 50},
    ]
    teams = form_teams(people, reqs, team_size=3)["teams"]
    assert len(teams) == 2 and all(len(t["members"]) == 3 for t in teams)
    assert all(t["coverage"] == 100.0 for t in teams)  # each team gets React + Python + Docker
    assert {m["role"] for t in teams for m in t["members"]} == {"React", "Python", "Docker"}
