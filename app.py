# AI Recruiter PRO — v16
# Scoring fiabilisé (règles déterministes + IA hybride + Ollama local)
# -------------------------------------------------------------------

from __future__ import annotations

import streamlit as st
import json, io, re, uuid, time
import datetime as dt
from typing import Optional, Dict, List, Any, Tuple
from copy import deepcopy

# LLM (Groq-compatible OpenAI SDK)
import openai

# PDF
from pypdf import PdfReader
try:
    from pdfminer.high_level import extract_text as pdfminer_extract
except Exception:
    pdfminer_extract = None

# Data / viz
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

# Validation
from pydantic import BaseModel, Field, ValidationError, conint, constr

# Local LLM (gratuit)
import requests


# -----------------------------
# 0. PAGE CONFIG & THEME
# -----------------------------
st.set_page_config(page_title="AI Recruiter PRO v16", layout="wide", page_icon="🎯", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    :root {
        --primary:#1d4ed8; --success:#16a34a; --warning:#b45309; --danger:#b91c1c;
        --text-main:#0f172a; --text-sub:#334155; --bg-app:#f8fafc; --border:#94a3b8;
    }
    .stApp { background: var(--bg-app); color: var(--text-main); }
    .kpi-card { background:#fff; padding:20px; border:1px solid var(--border); border-radius:8px; text-align:center; position:relative; }
    .kpi-card::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;border-radius:8px 8px 0 0}
    .kpi-card.primary::before{background:var(--primary)}
    .kpi-card.success::before{background:var(--success)}
    .kpi-card.warning::before{background:var(--warning)}
    .kpi-val{font-size:1.6rem;font-weight:700}
    .kpi-label{font-size:.8rem;color:#475569;text-transform:uppercase;font-weight:600}
    .score-badge{display:inline-flex;align-items:center;justify-content:center;width:60px;height:60px;border-radius:50%;font-weight:800;font-size:1.1rem;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.45)}
    .score-high{background:linear-gradient(135deg,#059669,#065f46)}
    .score-mid{background:linear-gradient(135deg,#9a3412,#7c2d12)}
    .score-low{background:linear-gradient(135deg,#b91c1c,#7f1d1d)}
    .verdict{background:#eef2ff;padding:15px;border-radius:8px;font-weight:500;border-left:4px solid var(--primary);margin-bottom:20px}
    .skill-tag{background:#f1f5f9;border:1px solid var(--border);color:var(--text-main);padding:4px 10px;border-radius:4px;font-size:.8rem;margin:2px;display:inline-block;font-weight:500}
    .match{background:#ecfdf5;border-color:#34d399;color:#065f46}
    .missing{background:#fff7ed;border-color:#fdba74;color:#7c2d12;text-decoration:line-through}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 1. SCHEMA Pydantic
# -----------------------------
class Infos(BaseModel):
    nom: str = "Candidat"; email: str = ""; tel: str = ""; ville: str = ""; linkedin: str = ""; poste_actuel: str = ""

class Scores(BaseModel):
    global_: conint(ge=0, le=100) = Field(0, alias="global")
    tech: conint(ge=0, le=100) = 0
    experience: conint(ge=0, le=100) = 0
    soft: conint(ge=0, le=100) = 0
    fit: conint(ge=0, le=100) = 0
    class Config: allow_population_by_field_name = True

class Salaire(BaseModel):
    min: int = 0; max: int = 0; confiance: constr(strip_whitespace=True) = ""; analyse: str = "Non estimé"

class HistoriqueItem(BaseModel):
    titre: str; entreprise: str = ""; duree: str = ""; resume_synthetique: str = ""

class QuestionItem(BaseModel):
    theme: str = "Général"; question: str = ""; attendu: str = ""

class Analyse(BaseModel):
    verdict: str = "En attente"; points_forts: List[str] = []; points_faibles: List[str] = []

class Competences(BaseModel):
    match: List[str] = []; manquant: List[str] = []

class CandidateData(BaseModel):
    infos: Infos = Infos()
    scores: Scores = Scores()
    salaire: Salaire = Salaire()
    analyse: Analyse = Analyse()
    competences: Competences = Competences()
    historique: List[HistoriqueItem] = []
    entretien: List[QuestionItem] = []

DEFAULT_DATA = CandidateData().dict(by_alias=True)


# -----------------------------
# 2. OUTILS
# -----------------------------
@st.cache_resource(show_spinner=False)
def get_client() -> Optional[openai.OpenAI]:
    try:
        key = st.secrets.get("GROQ_API_KEY")
        if not key:
            st.error("❌ Clé API GROQ_API_KEY manquante dans Secrets.")
            return None
        return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key, timeout=30.0)
    except Exception as e:
        st.error(f"❌ Erreur initialisation API: {e}")
        return None

def _clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()

def extract_pdf_safe(file_bytes: bytes) -> Optional[str]:
    try:
        stream = io.BytesIO(file_bytes); reader = PdfReader(stream); chunks = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text: chunks.append(page_text)
        text = "\n".join(chunks).strip()
        if not text and pdfminer_extract:
            text = pdfminer_extract(io.BytesIO(file_bytes)) or ""
        return _clean_text(text)
    except Exception:
        if pdfminer_extract:
            try: return _clean_text(pdfminer_extract(io.BytesIO(file_bytes)) or "")
            except Exception: return None
        return None

def normalize_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return CandidateData.parse_obj(raw).dict(by_alias=True)
    except ValidationError:
        safe = deepcopy(DEFAULT_DATA)
        i = raw.get("infos", {}) or {}
        for k in safe["infos"].keys():
            if k in i: safe["infos"][k] = i[k]
        sc = raw.get("scores", {}) or {}
        for k in ["global", "tech", "experience", "soft", "fit"]:
            if k in sc and isinstance(sc[k], (int, float)):
                safe["scores"][k] = max(0, min(100, int(sc[k])))
        sal = raw.get("salaire", {}) or {}
        for k in safe["salaire"].keys():
            if k in sal: safe["salaire"][k] = sal[k]
        ana = raw.get("analyse", {}) or {}
        for k in safe["analyse"].keys():
            if k in ana: safe["analyse"][k] = ana[k]
        comp = raw.get("competences", {}) or {}
        for k in safe["competences"].keys():
            if k in comp: safe["competences"][k] = comp[k]
        safe_hist = []
        for h in raw.get("historique", []) or []:
            safe_hist.append({
                "titre": str(h.get("titre", "Poste")),
                "entreprise": str(h.get("entreprise", "")),
                "duree": str(h.get("duree", "")),
                "resume_synthetique": str(h.get("resume_synthetique", h.get("mission", ""))),
            })
        safe["historique"] = safe_hist
        safe_q = []
        for q in raw.get("entretien", []) or []:
            safe_q.append({"theme": str(q.get("theme", "Général")), "question": str(q.get("question", "")), "attendu": str(q.get("attendu", ""))})
        safe["entretien"] = safe_q
        return safe


# -----------------------------
# 2.b. MOTEUR DE RÈGLES (gratuit) + OLLAMA LOCAL
# -----------------------------
SKILL_SYNONYMS = {
    "python":["python"],"java":["java"],
    "javascript":["javascript","js","node.js","nodejs"],"typescript":["typescript","ts"],
    "sql":["sql","mysql","postgres","postgresql","t-sql","pl/sql","sqlite","mariadb"],
    "aws":["aws","amazon web services","ec2","s3","lambda","rds","cloudformation","eks"],
    "gcp":["gcp","google cloud","bigquery","gke","dataproc"],"azure":["azure"],
    "docker":["docker","containers"],"kubernetes":["kubernetes","k8s"],
    "django":["django"],"flask":["flask"],"react":["react","reactjs"],"vue":["vue","vuejs"],
    "spark":["spark","pyspark"],
    "ml":["machine learning","ml","scikit-learn","sklearn","pytorch","tensorflow"],
    "nlp":["nlp","spacy","transformers","bert"],
    "git":["git","github","gitlab"],"agile":["agile","scrum","kanban"],
    "anglais":["anglais","english","b2","c1","courant"],
}
SKILL_INDEX = {w.lower():canon for canon, syns in SKILL_SYNONYMS.items() for w in set([canon, *syns])}
SOFT_HINTS = ["communication","collabor","leadership","autonomie","rigueur","organisation","team","client","pédagogue","problem","créatif","curiosit","empathie","ownership"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?){4,6}\d{2}")
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.[A-Za-z]{2,3}/[A-Za-z0-9_\-/]+", re.I)

CEFR_RE = re.compile(r"\b(A1|A2|B1|B2|C1|C2)\b", re.I)
BAC_RE = re.compile(r"bac\s*\+\s*(\d)", re.I)
MASTER_RE = re.compile(r"\b(master|msc|m\.sc\.)\b", re.I)
PHD_RE = re.compile(r"\b(doctorat|phd)\b", re.I)

YEARSPAN_RE = re.compile(r"(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|19\d{2}|présent|present|now)", re.I)
YEARS_RE = re.compile(r"(\d+)\s*(?:\+?\s*)?(?:ans|years?)", re.I)

def extract_pii_from_cv(text: str) -> Dict[str, str]:
    email = EMAIL_RE.search(text); phone = PHONE_RE.search(text); li = LINKEDIN_RE.search(text)
    return {"nom":"Candidat","email":email.group(0) if email else "","tel":phone.group(0) if phone else "","ville":"", "linkedin":li.group(0) if li else "","poste_actuel":""}

def extract_years(text: str) -> Optional[float]:
    nums = [float(m.group(1)) for m in YEARS_RE.finditer(text)]
    max_exp = max(nums) if nums else 0.0
    now_y = dt.date.today().year
    for m in YEARSPAN_RE.finditer(text):
        a = m.group(1); b = m.group(2)
        y1 = int(a); y2 = now_y if b.lower() in ("présent","present","now") else int(b)
        if y2 >= y1: max_exp = max(max_exp, float(y2 - y1))
    return max_exp if max_exp else None

def extract_skills_set(text: str) -> set:
    low = text.lower(); found = set()
    for syn, canon in SKILL_INDEX.items():
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(syn)}(?![A-Za-z0-9_])", low):
            found.add(canon)
    return found

def parse_must_haves(criteria: str) -> Dict[str, Any]:
    tokens = [t.strip().lower() for t in re.split(r"[,;\n]", criteria or "") if t.strip()]
    must = {"skills": [], "min_years": None, "lang": None, "degree": None, "remote": None, "location": None}
    for t in tokens:
        # années
        m = YEARS_RE.search(t)
        if m:
            must["min_years"] = max(int(m.group(1)), must["min_years"] or 0)
            continue
        # langue CEFR
        m2 = CEFR_RE.search(t)
        if m2:
            must["lang"] = m2.group(1).upper()
            continue
        # diplômes
        if BAC_RE.search(t): must["degree"] = max(int(BAC_RE.search(t).group(1)), must["degree"] or 0)
        if MASTER_RE.search(t): must["degree"] = max(5, must["degree"] or 0)
        if PHD_RE.search(t): must["degree"] = 8
        # remote / localisation
        if "remote" in t or "télétravail" in t: must["remote"] = True
        if "paris" in t or "idf" in t: must["location"] = "paris"
        # compétences
        if t in SKILL_INDEX: must["skills"].append(SKILL_INDEX[t])
        else:
            hit = next((SKILL_INDEX[k] for k in SKILL_INDEX if t in k), None)
            if hit: must["skills"].append(hit)
    must["skills"] = list(dict.fromkeys(must["skills"]))  # dedupe
    return must

def level_ok(cv_text: str, level: Optional[str]) -> bool:
    if not level: return True
    order = {"A1":1,"A2":2,"B1":3,"B2":4,"C1":5,"C2":6}
    found = CEFR_RE.findall(cv_text)
    if not found: return False
    return max(order.get(x.upper(),0) for x in found) >= order.get(level,0)

def degree_ok(cv_text: str, required: Optional[int]) -> bool:
    if not required: return True
    b = BAC_RE.search(cv_text); m = MASTER_RE.search(cv_text); p = PHD_RE.search(cv_text)
    level = 0
    if b: level = max(level, int(b.group(1)))
    if m: level = max(level, 5)
    if p: level = max(level, 8)
    return level >= required

def compute_rule_based(job: str, cv: str, criteria: str, weights: Tuple[float,float,float,float]) -> Dict[str, Any]:
    skills_job = extract_skills_set(job)
    skills_cv  = extract_skills_set(cv)
    must = parse_must_haves(criteria)

    match   = sorted(list(skills_cv & skills_job))
    missing = [m for m in must["skills"] if m not in skills_cv]

    tech_score = int(round(100 * (len(match) / max(1, len(skills_job))))) if skills_job else (80 if match else 40)

    req_years = must.get("min_years") or extract_years(job) or 0
    cv_years  = extract_years(cv) or 0
    if req_years:
        ratio = min(1.4, (cv_years or 0.0)/req_years)
        exp_score = int(round(100 * min(1.0, 0.55*ratio + 0.45)))
    else:
        exp_score = 70 if cv_years else 50

    soft_hits  = sum(1 for h in SOFT_HINTS if h in cv.lower())
    soft_score = min(100, 50 + soft_hits*8)

    fit_score = 72
    if ("remote" in job.lower() or "télétravail" in job.lower()):
        fit_score += 8 if ("remote" in cv.lower() or "télétravail" in cv.lower()) else -6
    if must.get("lang") and not level_ok(cv, must["lang"]):
        fit_score -= 15
        missing.append(f"anglais {must['lang']}+")
    if must.get("degree") and not degree_ok(cv, must["degree"]):
        fit_score -= 10
        missing.append(f"diplôme bac+{must['degree']}")

    global_rule = int(round(tech_score*weights[0] + exp_score*weights[1] + soft_score*weights[2] + fit_score*weights[3]))

    # Gate dur si must-have manquant
    if missing:
        global_rule = min(global_rule, 49)

    infos = extract_pii_from_cv(cv)
    analysis_pf = [f"Compétences: {', '.join(match[:6])}"] if match else []
    analysis_pr = [f"Manquants: {', '.join(missing[:6])}"] if missing else []

    return {
        "infos": infos,
        "scores": {"global": global_rule, "tech": tech_score, "experience": exp_score, "soft": soft_score, "fit": fit_score},
        "salaire": {"min": 0, "max": 0, "confiance": "Basse", "analyse": "Non estimé (mode règles)"},
        "competences": {"match": match, "manquant": missing},
        "analyse": {"verdict": "Scoring déterministe (règles)", "points_forts": analysis_pf, "points_faibles": analysis_pr},
        "historique": [],
        "entretien": [],
    }


# -----------------------------
# 3. LLM (Groq / Ollama) + HYBRIDE
# -----------------------------
SCORING_PROMPT = """
ROLE: Expert Recrutement (exigeant et précis). Réponds UNIQUEMENT en JSON valide.
BARÈME:
- GLOBAL (0-100) = Tech (40%) + Exp (30%) + Soft (15%) + Fit (15%).
- Si compétence critique manquante ⇒ GLOBAL < 50.
- 80+ Excellent | 60–79 Bon | 40–59 Moyen | <40 Inadéquat.
SALAIRE (France 2025, k€ brut/an) : ajuste selon séniorité, région (Paris +15%), rareté des skills.
Schéma JSON: infos, scores, salaire, competences, analyse, historique, entretien.
"""

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_with_groq(job: str, cv: str, criteria: str, file_id: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    if not client: return None
    job_c, cv_c = job[:2000], cv[:4000]
    user_prompt = f"""
ID: {file_id}
{SCORING_PROMPT}

OFFRE:\n{job_c}\n\nCRITERES CRITIQUES:\n{criteria}\n\nCV:\n{cv_c}
"""
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content": user_prompt}],
            response_format={"type":"json_object"}, temperature=0.0, max_tokens=2200,
        )
        raw = json.loads(res.choices[0].message.content)
        return normalize_json(raw)
    except Exception as e:
        st.info(f"ℹ️ Groq indisponible: {e}")
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def analyze_with_ollama(job: str, cv: str, criteria: str, file_id: str, model_name: str = "llama3.1:8b") -> Optional[Dict[str, Any]]:
    job_c, cv_c = job[:2000], cv[:4000]
    prompt = f"""
ID: {file_id}
{SCORING_PROMPT}

OFFRE:\n{job_c}\n\nCRITERES CRITIQUES:\n{criteria}\n\nCV:\n{cv_c}
"""
    try:
        payload = {"model": model_name, "messages": [{"role":"user","content": prompt}], "options": {"temperature":0, "num_ctx":8192, "format":"json"}}
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=90)
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "{}").strip()
        raw = json.loads(content)
        return normalize_json(raw)
    except Exception as e:
        st.info(f"ℹ️ Ollama indisponible: {e}")
        return None

def recompute_global(score: Dict[str, int], weights: Tuple[float, float, float, float]) -> int:
    tech, exp, soft, fit = score.get("tech",0), score.get("experience",0), score.get("soft",0), score.get("fit",0)
    return int(round(tech*weights[0] + exp*weights[1] + soft*weights[2] + fit*weights[3]))

def analyze_candidate(job: str, cv: str, criteria: str, file_id: str, provider: str, model_name: str, mode: str, weights: Tuple[float,float,float,float], alpha_rules: float) -> Optional[Dict[str, Any]]:
    mode_l = (mode or "").lower()
    if provider == "none" or "règles" in mode_l:
        return compute_rule_based(job, cv, criteria, weights)

    llm = analyze_with_groq(job, cv, criteria, file_id) if provider == "groq" else analyze_with_ollama(job, cv, criteria, file_id, model_name=model_name)
    if not llm:
        return compute_rule_based(job, cv, criteria, weights)

    if "ia uniquement" in mode_l:
        llm["scores"]["global"] = recompute_global(llm["scores"], weights)
        return llm

    # Hybride
    rules = compute_rule_based(job, cv, criteria, weights)
    sL, sR = llm["scores"], rules["scores"]
    combined = {
        "tech":       int(round(alpha_rules*sR.get("tech",0)       + (1-alpha_rules)*sL.get("tech",0))),
        "experience": int(round(alpha_rules*sR.get("experience",0) + (1-alpha_rules)*sL.get("experience",0))),
        "soft":       int(round(alpha_rules*sR.get("soft",0)       + (1-alpha_rules)*sL.get("soft",0))),
        "fit":        int(round(alpha_rules*sR.get("fit",0)        + (1-alpha_rules)*sL.get("fit",0))),
    }
    combined["global"] = recompute_global(combined, weights)

    # Gate si règles indiquent manquants critiques
    if rules["competences"].get("manquant"):
        combined["global"] = min(combined["global"], 49)

    match_union   = sorted(list(set(rules["competences"].get("match",[])) | set(llm["competences"].get("match",[]))))
    missing_rules = rules["competences"].get("manquant", [])

    verdict = llm.get("analyse", {}).get("verdict", "") or "Évaluation hybride"
    pf = list(dict.fromkeys([*(llm.get("analyse", {}).get("points_forts", []) or []), f"Match règles: {', '.join(match_union[:5])}"]))[:5]
    pr = list(dict.fromkeys([*(llm.get("analyse", {}).get("points_faibles", []) or []), *([f"Manquants (règles): {', '.join(missing_rules[:5])}"] if missing_rules else [])]))[:5]

    out = deepcopy(llm)
    out["scores"] = combined
    out["competences"] = {"match": match_union, "manquant": missing_rules}
    out["analyse"] = {"verdict": verdict + " (hybride)", "points_forts": pf, "points_faibles": pr}

    if not (out["infos"].get("email") or out["infos"].get("tel") or out["infos"].get("linkedin")):
        out["infos"].update(extract_pii_from_cv(cv))
    return out


# -----------------------------
# 4. PERSISTENCE (facultatif)
# -----------------------------
def save_to_sheets(data: Dict[str, Any], job_desc: str) -> None:
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
    except Exception:
        return
    try:
        svc = st.secrets.get("gcp_service_account")
        if not svc: return
        scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(svc), scope)
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        i, s = data["infos"], data["scores"]
        sheet.append_row([dt.datetime.now().strftime("%Y-%m-%d %H:%M"), i.get("nom",""), f"{s.get('global',0)}%", i.get("email",""), i.get("linkedin",""), _clean_text(job_desc)[:80]])
    except Exception as e:
        st.info(f"ℹ️ Sheets non accessible: {e}")

def export_to_excel(results: List[Dict[str, Any]]) -> bytes:
    flat = []
    for r in results:
        i, s, sal = r["infos"], r["scores"], r["salaire"]
        comp = r.get("competences", {})
        flat.append({
            "Nom": i.get("nom",""), "Email": i.get("email",""), "Tel": i.get("tel",""), "Ville": i.get("ville",""),
            "LinkedIn": i.get("linkedin",""), "Poste Actuel": i.get("poste_actuel",""),
            "Score Global": s.get("global",0), "Score Tech": s.get("tech",0), "Score Exp": s.get("experience",0), "Score Soft": s.get("soft",0), "Score Fit": s.get("fit",0),
            "Salaire Min": sal.get("min",0), "Salaire Max": sal.get("max",0),
            "Verdict": r.get("analyse",{}).get("verdict",""),
            "Compétences Match": ", ".join(comp.get("match",[])), "Compétences Manquantes": ", ".join(comp.get("manquant",[])),
        })
    df = pd.DataFrame(flat)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Candidats")
    return out.getvalue()


# -----------------------------
# 5. SIDEBAR
# -----------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    ao_file = st.file_uploader("1️⃣ Offre d'emploi (PDF)", type="pdf", key="ao")
    ao_text = st.text_area("Ou coller le texte", height=100, placeholder="Description du poste…")
    job_text = extract_pdf_safe(ao_file.getvalue()) if ao_file else (ao_text or "")

    criteria = st.text_area("2️⃣ Critères Non-Négociables", height=80, placeholder="Ex: Anglais C1, Python expert, 5+ ans, Bac+5, télétravail…")

    st.subheader("⚖️ Pondérations")
    w_tech = st.slider("Tech %", 0, 100, 40)
    w_exp  = st.slider("Expérience %", 0, 100, 30)
    w_soft = st.slider("Soft %", 0, 100, 15)
    w_fit  = st.slider("Fit %", 0, 100, 15)
    total_w = w_tech + w_exp + w_soft + w_fit
    if total_w != 100: st.warning(f"Les pondérations totalisent {total_w}%. Elles seront normalisées.")

    st.subheader("🔌 Moteur & mode")
    backend_choice = st.selectbox("Moteur d'analyse", ["Groq • Llama 3.3 70B", "Ollama local • llama3.1:8b", "Sans IA (règles uniquement — gratuit)"])
    mode_choice = st.radio("Mode de scoring", ["Hybride (règles + IA)", "IA uniquement", "Règles uniquement (gratuit)"], index=0)
    alpha_rules = st.slider("Poids des règles (hybride)", 0, 100, 60)

    def _resolve_backend(name: str) -> Tuple[str, str]:
        if name.startswith("Groq"): return "groq", "llama-3.3-70b-versatile"
        if name.startswith("Ollama"): return "ollama", "llama3.1:8b"
        return "none", ""
    provider, model_name = _resolve_backend(backend_choice)

    cv_files = st.file_uploader("3️⃣ CVs Candidats (PDF)", type="pdf", accept_multiple_files=True)

    st.subheader("🔒 Options")
    anonymize = st.checkbox("Anonymiser l'affichage (PII masquées)", value=False)
    dedupe_on = st.checkbox("Dédoublonner par email/téléphone", value=True)
    max_workers = st.number_input("Concurrence (threads)", min_value=1, max_value=8, value=3, step=1)
    qualify_threshold = st.slider("Seuil qualifié (Score ≥)", 0, 100, 70)

    # Mode debug pour voir JSON/erreurs dans la fiche
    debug_mode = st.checkbox("Mode debug (afficher JSON et erreurs)", value=False)
    st.session_state["debug"] = debug_mode

    st.divider()
    c1, c2 = st.columns(2)
    launch_btn = c1.button("🚀 Analyser", type="primary", use_container_width=True)
    reset_btn  = c2.button("🗑️ Reset", use_container_width=True)
    if reset_btn: st.session_state.clear(); st.rerun()

    with st.expander("ℹ️ Aide"):
        st.caption("""
        **Modes** : Règles = gratuit et déterministe • Ollama = gratuit local • Hybride = robuste.
        **Gate** : Must-have manquant ⇒ score global ≤ 49.
        """)

# State
if "results" not in st.session_state: st.session_state["results"] = []
if "raw_store" not in st.session_state: st.session_state["raw_store"] = {}


# -----------------------------
# 6. LOGIQUE
# -----------------------------
def _normalize_weights(t: Tuple[int,int,int,int]) -> Tuple[float,float,float,float]:
    s = sum(t);  return (0.4,0.3,0.15,0.15) if s<=0 else tuple(x/s for x in t)  # type: ignore

def hash_identity(email: str, tel: str) -> str:
    base = (email or "").strip().lower() + "|" + re.sub(r"\D", "", tel or "")
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, base or str(uuid.uuid4())))

def anonymize_infos(i: Dict[str, Any]) -> Dict[str, Any]:
    ret = dict(i)
    if ret.get("email"): ret["email"] = re.sub(r"(^.).+(@.+$)", r"\\1***\\2", ret["email"])  # a***@domaine
    if ret.get("tel"):
        t = re.sub(r"\D", "", ret["tel"])
        ret["tel"] = "✱✱✱✱ " + (t[-4:] if len(t)>=4 else "✱✱✱✱")
    if ret.get("linkedin"): ret["linkedin"] = "(lien)"
    return ret

def process_single_cv(file_obj, job_text: str, criteria: str, weights: Tuple[float,float,float,float], provider: str, model_name: str, mode_choice: str, alpha_rules: int) -> Optional[Dict[str, Any]]:
    file_bytes = file_obj.getvalue(); cv_text = extract_pdf_safe(file_bytes) or ""
    if len(cv_text) < 50:
        st.warning(f"⚠️ {file_obj.name}: contenu insuffisant.")
        return None
    file_id = str(uuid.uuid4())
    data = analyze_candidate(job_text, cv_text, criteria, file_id=file_id, provider=provider, model_name=model_name, mode=mode_choice, weights=weights, alpha_rules=alpha_rules/100.0)
    return data

if launch_btn:
    if not job_text or len(job_text) < 50:
        st.error("⚠️ L'offre doit contenir au moins 50 caractères.")
    elif not cv_files:
        st.error("⚠️ Ajoutez au moins un CV.")
    else:
        weights = _normalize_weights((w_tech, w_exp, w_soft, w_fit))
        results: List[Dict[str, Any]] = []
        progress = st.empty(); bar = st.progress(0)
        with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
            futures = [ex.submit(process_single_cv, f, job_text, criteria, weights, provider, model_name, mode_choice, alpha_rules) for f in cv_files]
            done = 0
            for fut in as_completed(futures):
                res = fut.result(); done += 1
                if res:
                    if dedupe_on:
                        identity = hash_identity(res["infos"].get("email",""), res["infos"].get("tel",""))
                        prev = st.session_state["raw_store"].get(identity)
                        if not prev or res["scores"]["global"] > prev["scores"]["global"]:
                            st.session_state["raw_store"][identity] = res
                    else:
                        results.append(res)
                bar.progress(done / len(futures)); progress.text(f"📄 {done}/{len(futures)} CV traités…")
        progress.empty(); bar.empty()
        if dedupe_on: results = list(st.session_state["raw_store"].values())
        for d in results: save_to_sheets(d, job_text)
        st.session_state["results"] = results
        if results: st.success(f"✅ {len(results)} candidat(s) analysé(s) !"); st.rerun()
        else: st.error("❌ Aucune analyse n'a abouti. Vérifiez vos PDF.")


# -----------------------------
# 7. VUES
# -----------------------------
results: List[Dict[str, Any]] = st.session_state.get("results", []) or []
if not results:
    st.markdown("""
        <div style="text-align:center; padding:80px 20px;">
            <h1 style="color:var(--text-main); font-weight:800;">AI Recruiter PRO v16</h1>
            <p style="color:var(--text-sub); font-size:1.1rem;">Analyse intelligente de candidatures</p>
            <div style="margin-top:50px; opacity:0.6;">👈 Configurez dans la barre latérale pour commencer</div>
        </div>
    """, unsafe_allow_html=True)
else:
    results_sorted = sorted(results, key=lambda x: x["scores"]["global"], reverse=True)
    avg = int(round(sum(r["scores"]["global"] for r in results_sorted) / max(1, len(results_sorted))))
    top = results_sorted[0]["scores"]["global"]
    qualify_threshold = st.session_state.get("qualify_threshold", 70) if "qualify_threshold" in st.session_state else 70
    qualified_count = len([x for x in results_sorted if x["scores"]["global"] >= qualify_threshold])

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{len(results_sorted)}</div><div class="kpi-label">Candidats</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="kpi-card success"><div class="kpi-val">{qualified_count}</div><div class="kpi-label">Qualifiés (≥ {qualify_threshold}%)</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class="kpi-card warning"><div class="kpi-val">{avg}%</div><div class="kpi-label">Score moyen</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{top}%</div><div class="kpi-label">Top candidat</div></div>""", unsafe_allow_html=True)

    st.write("")
    left, mid, right = st.columns([2,1,2])
    with left:
        filter_val = st.selectbox("Filtrer par score", options=[0,40,60,70,80], format_func=lambda x: "Tous" if x==0 else f"Score ≥ {x}%")
    with mid:
        if st.button("📥 Exporter Excel", use_container_width=True):
            excel_data = export_to_excel(results_sorted)
            st.download_button("💾 Télécharger", data=excel_data, file_name=f"candidats_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with right:
        names = [r["infos"].get("nom", f"Candidat {i+1}") for i,r in enumerate(results_sorted)]
        try:
            comp_sel = st.multiselect("Comparer (max 3)", options=names, default=names[:0], max_selections=3)
        except TypeError:
            # fallback pour versions Streamlit sans max_selections
            comp_sel = st.multiselect("Comparer", options=names, default=names[:0])

    st.divider()

    if comp_sel:
        sel = [r for r in results_sorted if r["infos"].get("nom","") in comp_sel]
        if sel:
            cols = st.columns(len(sel))
            for j, d in enumerate(sel):
                i, s = d["infos"], d["scores"]
                cols[j].markdown(f"**{i.get('nom','Candidat')} — {s.get('global',0)}%**")
                cat = ['Tech','Exp','Soft','Fit','Tech']
                val = [s.get('tech',0), s.get('experience',0), s.get('soft',0), s.get('fit',0), s.get('tech',0)]
                fig = go.Figure(go.Scatterpolar(r=val, theta=cat, fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])), showlegend=False, height=260, margin=dict(t=10,b=10,l=10,r=10))
                cols[j].plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.divider()

    filtered = [r for r in results_sorted if r["scores"]["global"] >= filter_val]
    if not filtered: st.warning(f"Aucun candidat avec un score ≥ {filter_val}%")

    for idx, d in enumerate(filtered):
        i = d["infos"]; s = d["scores"]
        i_disp = anonymize_infos(i) if st.session_state.get("anonymize", False) else (anonymize_infos(i) if 'anonymize' in locals() and anonymize else i)

        if s.get("global", 0) >= 75:
            score_class, score_emoji = "score-high", "🌟"
        elif s.get("global", 0) >= 50:
            score_class, score_emoji = "score-mid", "⚡"
        else:
            score_class, score_emoji = "score-low", "⚠️"

        with st.expander(f"{score_emoji} {i_disp.get('nom','Candidat')} — {s.get('global',0)}%", expanded=(idx == 0)):
            if st.session_state.get("debug"):
                st.caption("DEBUG: données brutes du candidat")
                st.json(d)
            try:
                # Header
                st.markdown(
                    f"""
                    <div style='display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:12px;border-bottom:1px solid #f1f5f9;margin-bottom:12px;'>
                        <div>
                            <h3 style='margin:0'>{i_disp.get('nom','Candidat')}</h3>
                            <div style='color:#334155'>{i_disp.get('poste_actuel','')} • {i_disp.get('ville','')}</div>
                            <div style='margin-top:10px;'>
                                <span class='skill-tag'>📧 {i_disp.get('email','')}</span>
                                <span class='skill-tag'>📞 {i_disp.get('tel','')}</span>
                                <span class='skill-tag'>🔗 {i_disp.get('linkedin','')}</span>
                            </div>
                        </div>
                        <div class='score-badge {score_class}'>{s.get('global',0)}%</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(f"""<div class='verdict'>💡 <strong>Verdict:</strong> {d.get('analyse',{}).get('verdict','')}</div>""", unsafe_allow_html=True)

                # Points forts / Vigilance
                cA, cB = st.columns(2)
                with cA:
                    forces = d.get("analyse", {}).get("points_forts", [])[:5]
                    st.markdown("**Points forts**")
                    for f in forces:
                        st.write("✅ ", f)
                with cB:
                    risks = d.get("analyse", {}).get("points_faibles", [])[:5]
                    st.markdown("**Vigilance**")
                    for r in risks:
                        st.write("❗ ", r)

                st.divider()
                left, right = st.columns([2,1])

                with left:
                    st.markdown("#### 📅 Parcours Professionnel")
                    hist = d.get("historique", [])
                    if hist:
                        for h in hist[:4]:
                            titre = h.get('titre',''); ent = h.get('entreprise',''); duree = h.get('duree',''); res = h.get('resume_synthetique','')
                            st.markdown(f"""**{titre}** @ {ent} — {duree}
> _{res}_""")
                    else:
                        st.caption("Historique non disponible")

                with right:
                    sal = d.get("salaire", {})
                    st.markdown(
                        f"""
                        <div style='padding:12px;border:1px solid #e2e8f0;border-radius:8px;background:white;text-align:center;'>
                            <div style='font-size:0.75rem;color:#334155;text-transform:uppercase;'>Salaire Estimé</div>
                            <div style='font-size:1.5rem;font-weight:800;color:var(--text-main);'>{sal.get('min',0)}–{sal.get('max',0)} k€</div>
                            <div style='font-size:0.8rem;color:var(--primary);margin-top:4px;'>{sal.get('confiance','')}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    # Radar
                    cat = ['Tech', 'Exp', 'Soft', 'Fit', 'Tech']
                    val = [s.get('tech',0), s.get('experience',0), s.get('soft',0), s.get('fit',0), s.get('tech',0)]
                    fig = go.Figure(go.Scatterpolar(r=val, theta=cat, fill='toself'))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=240, margin=dict(t=10,b=10,l=10,r=10))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # Skills
                st.markdown("#### 🛠️ Compétences")
                comp = d.get("competences", {})
                skills_html = "".join([f"<span class='skill-tag match'>✓ {sk}</span>" for sk in comp.get("match", [])])
                skills_html += "".join([f"<span class='skill-tag missing'>{sk}</span>" for sk in comp.get("manquant", [])])
                st.markdown(skills_html, unsafe_allow_html=True)

                with st.expander("🎯 Guide d'entretien"):
                    for q in d.get("entretien", [])[:6]:
                        theme = q.get("theme", "Général")
                        st.markdown(f"**{theme}** — {q.get('question','')}\n\n> Attendu : _{q.get('attendu','')}_")

            except Exception as e:
                st.error(f"Affichage de la fiche impossible : {e}")
                if st.session_state.get("debug"):
                    st.exception(e)

            if st.session_state.get("debug"):
                st.caption("FIN DE FICHE — DEBUG")
                st.json(d)


# -----------------------------
# 8. NOTES DE PROD (facultatif)
# -----------------------------
with st.expander("🏭 Conseils de mise en prod (checklist)"):
    st.markdown("""
- Auth multi-tenant • DB managée • Journalisation & audit prompts • RGPD (export/suppression)
- Observabilité (Sentry) • Cache agressif • Limites de taille PDF • Tests parseurs/normaliseur
- Déploiement Docker (Cloud Run/Render/Fly.io)
    """)
