# AI Recruiter PRO — v15
# Plateforme Streamlit durcie + fonctionnalités avancées
# ----------------------------------------------------
# Points forts vs v14
# - Architecture + lisibilité : schéma Pydantic, normalisation robuste, deepcopy fix
# - Concurrence : traitement des CV en parallèle (ThreadPoolExecutor)
# - Pondérations ajustables : sliders pour Tech/Exp/Soft/Fit + seuils de qualification
# - Dédoublonnage PII : hash basé sur email/téléphone, anonymisation optionnelle UI
# - Guardrails LLM : JSON schema, validation stricte, repli tolérant
# - Fallback extraction PDF (pdfminer si dispo), nettoyage texte
# - Comparaison de candidats + vues supplémentaires (pipeline, notes)
# - Persistance : export Excel (amélioré), en option CSV/SQLite
# - Intégration Google Sheets conservée mais facultative
# - UX : toasts, états, contrôles reset/restore, + petits raffinements visuels
# - Sécurité : pas de mutation du DEFAULT_DATA, masquage des secrets, logs sobres

from __future__ import annotations

import streamlit as st
import json
import io
import re
import uuid
import time
import datetime as dt
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from copy import deepcopy

# LLM (Groq-compatible OpenAI SDK)
import openai

# PDF
from pypdf import PdfReader

# Optional fallback
try:
    from pdfminer.high_level import extract_text as pdfminer_extract
except Exception:  # pragma: no cover
    pdfminer_extract = None

# Data / viz
import pandas as pd
import plotly.graph_objects as go

# Async / concurrency
from concurrent.futures import ThreadPoolExecutor, as_completed

# Validation
from pydantic import BaseModel, Field, ValidationError, conint, constr

# Optional Sheets
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except Exception:  # pragma: no cover
    gspread = None
    ServiceAccountCredentials = None

# -----------------------------
# 0. PAGE CONFIG & THEME
# -----------------------------

st.set_page_config(
    page_title="AI Recruiter PRO v15",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded",
)

# CSS (reprend v14 + ajustements mineurs)
st.markdown(
    """
    <style>
    :root {
        --primary: #1d4ed8; /* bleu 700, meilleur contraste */
        --success: #16a34a; /* vert 600 */
        --warning: #b45309; /* ambre 700 */
        --danger:  #b91c1c; /* rouge 700 */
        --text-main: #0f172a; /* slate 900 */
        --text-sub:  #334155; /* slate 700 */
        --bg-app:    #f8fafc;
        --border:    #94a3b8; /* slate 400 */
    }
    .stApp { background-color: var(--bg-app); color: var(--text-main); }
    h1, h2, h3, h4, .stMarkdown, p, li, label { color: var(--text-main) !important; }

    /* KPI Cards */
    .kpi-card { background: #ffffff; padding: 20px; border: 1px solid var(--border); border-radius: 8px; text-align: center; height: 100%; position: relative; }
    .kpi-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px; border-radius: 8px 8px 0 0; }
    .kpi-card.primary::before { background: var(--primary); }
    .kpi-card.success::before { background: var(--success); }
    .kpi-card.warning::before { background: var(--warning); }
    .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--text-main); margin-bottom: 5px; }
    .kpi-label { font-size: 0.8rem; color: #475569; text-transform: uppercase; font-weight: 600; }

    /* Score badge (contraste renforcé) */
    .score-badge { display: inline-flex; align-items: center; justify-content: center; width: 60px; height: 60px; border-radius: 50%; font-weight: 800; font-size: 1.1rem; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,.45); }
    .score-high { background: linear-gradient(135deg, #059669, #065f46); }
    .score-mid  { background: linear-gradient(135deg, #9a3412, #7c2d12); }
    .score-low  { background: linear-gradient(135deg, #b91c1c, #7f1d1d); }

    /* Verdict lisible */
    .verdict { background: #eef2ff; color: var(--text-main); padding: 15px; border-radius: 8px; font-weight: 500; border-left: 4px solid var(--primary); margin-bottom: 20px; }

    /* Tags & skills (fond non-blanc + texte sombre) */
    .skill-tag { background: #f1f5f9; border: 1px solid var(--border); color: var(--text-main); padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; margin: 2px; display: inline-block; font-weight: 500; }
    .match   { background: #ecfdf5; border-color: #34d399; color: #065f46; }
    .missing { background: #fff7ed; border-color: #fdba74; color: #7c2d12; text-decoration: line-through; opacity: 1; }
</style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 1. MODELES Pydantic (schéma JSON strict)
# -----------------------------

class Infos(BaseModel):
    nom: str = "Candidat"
    email: str = ""
    tel: str = ""
    ville: str = ""
    linkedin: str = ""
    poste_actuel: str = ""

class Scores(BaseModel):
    global_: conint(ge=0, le=100) = Field(0, alias="global")
    tech: conint(ge=0, le=100) = 0
    experience: conint(ge=0, le=100) = 0
    soft: conint(ge=0, le=100) = 0
    fit: conint(ge=0, le=100) = 0

    class Config:
        allow_population_by_field_name = True

class Salaire(BaseModel):
    min: int = 0
    max: int = 0
    confiance: constr(strip_whitespace=True) = ""
    analyse: str = "Non estimé"

class HistoriqueItem(BaseModel):
    titre: str
    entreprise: str = ""
    duree: str = ""
    resume_synthetique: str = ""

class QuestionItem(BaseModel):
    theme: str = "Général"
    question: str = ""
    attendu: str = ""

class Analyse(BaseModel):
    verdict: str = "En attente"
    points_forts: List[str] = []
    points_faibles: List[str] = []

class Competences(BaseModel):
    match: List[str] = []
    manquant: List[str] = []

class CandidateData(BaseModel):
    infos: Infos = Infos()
    scores: Scores = Scores()
    salaire: Salaire = Salaire()
    analyse: Analyse = Analyse()
    competences: Competences = Competences()
    historique: List[HistoriqueItem] = []
    entretien: List[QuestionItem] = []

# Défault non mutable
DEFAULT_DATA = CandidateData().dict(by_alias=True)

# -----------------------------
# 2. OUTILS & HELPERS
# -----------------------------

@st.cache_resource(show_spinner=False)
def get_client() -> Optional[openai.OpenAI]:
    """Initialise le client Groq via SDK OpenAI-compatible."""
    try:
        key = st.secrets.get("GROQ_API_KEY")
        if not key:
            st.error("❌ Clé API GROQ_API_KEY manquante dans Secrets.")
            return None
        client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key, timeout=30.0)
        return client
    except Exception as e:
        st.error(f"❌ Erreur initialisation API: {e}")
        return None


def _clean_text(txt: str) -> str:
    txt = re.sub(r"\s+", " ", txt or "").strip()
    return txt


def extract_pdf_safe(file_bytes: bytes) -> Optional[str]:
    """Extraction texte PDF robuste avec fallback pdfminer (si présent)."""
    try:
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        chunks = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text:
                chunks.append(page_text)
        text = "\n".join(chunks).strip()
        if not text and pdfminer_extract:
            # Fallback si pypdf échoue
            text = pdfminer_extract(io.BytesIO(file_bytes)) or ""
        return _clean_text(text)
    except Exception as e:
        st.warning(f"⚠️ Erreur lecture PDF: {e}")
        if pdfminer_extract:
            try:
                return _clean_text(pdfminer_extract(io.BytesIO(file_bytes)) or "")
            except Exception:
                return None
        return None


def normalize_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Valide et normalise la sortie LLM via Pydantic. Tolère les écarts minimes."""
    try:
        model = CandidateData.parse_obj(raw)
        return model.dict(by_alias=True)
    except ValidationError:
        # Repli : on mappe manuellement les clés présentes
        safe = deepcopy(DEFAULT_DATA)
        # Infos
        i = raw.get("infos", {}) or {}
        for k in safe["infos"].keys():
            if k in i:
                safe["infos"][k] = i[k]
        # Scores
        sc = raw.get("scores", {}) or {}
        for k in ["global", "tech", "experience", "soft", "fit"]:
            if k in sc and isinstance(sc[k], (int, float)):
                safe["scores"][k] = max(0, min(100, int(sc[k])))
        # Salaire
        sal = raw.get("salaire", {}) or {}
        for k in safe["salaire"].keys():
            if k in sal:
                safe["salaire"][k] = sal[k]
        # Analyse, competences
        ana = raw.get("analyse", {}) or {}
        for k in safe["analyse"].keys():
            if k in ana:
                safe["analyse"][k] = ana[k]
        comp = raw.get("competences", {}) or {}
        for k in safe["competences"].keys():
            if k in comp:
                safe["competences"][k] = comp[k]
        # Historique
        safe_hist = []
        for h in raw.get("historique", []) or []:
            safe_hist.append({
                "titre": str(h.get("titre", "Poste")),
                "entreprise": str(h.get("entreprise", "")),
                "duree": str(h.get("duree", "")),
                "resume_synthetique": str(h.get("resume_synthetique", h.get("mission", ""))),
            })
        safe["historique"] = safe_hist
        # Entretien
        safe_q = []
        for q in raw.get("entretien", []) or []:
            safe_q.append({
                "theme": str(q.get("theme", "Général")),
                "question": str(q.get("question", "")),
                "attendu": str(q.get("attendu", "")),
            })
        safe["entretien"] = safe_q
        return safe


def hash_identity(email: str, tel: str) -> str:
    base = (email or "").strip().lower() + "|" + re.sub(r"\D", "", tel or "")
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, base or str(uuid.uuid4())))


def anonymize_infos(i: Dict[str, Any]) -> Dict[str, Any]:
    """Masque PII pour l'affichage (optionnel)."""
    ret = dict(i)
    if ret.get("email"):
        ret["email"] = re.sub(r"(^.).+(@.+$)", r"\1***\2", ret["email"])  # a***@domaine
    if ret.get("tel"):
        t = re.sub(r"\D", "", ret["tel"])  # digits only
        if len(t) >= 4:
            ret["tel"] = "✱✱✱✱ " + t[-4:]
        else:
            ret["tel"] = "✱✱✱✱"
    if ret.get("linkedin"):
        ret["linkedin"] = "(lien)"
    return ret


# -----------------------------
# 3. LLM CALL
# -----------------------------

SCORING_PROMPT = """
ROLE: Expert Recrutement (exigeant et précis), biais minimisés. Format STRICT JSON.

CONTRAINTE: Réponds UNIQUEMENT en JSON valide, sans texte hors JSON.

BARÈME:
- GLOBAL (0-100) = Tech (40%) + Exp (30%) + Soft (15%) + Fit (15%).
- Si compétence critique manquante ⇒ GLOBAL < 50.
- 80+ Excellent | 60–79 Bon | 40–59 Moyen | <40 Inadéquat.

SALAIRE (France 2025, k€ brut/an): ajuste selon séniorité, région (Paris +15%), rareté des skills.

CHAMPS (schéma):
{
  "infos": {"nom": "", "email": "", "tel": "", "ville": "", "linkedin": "", "poste_actuel": ""},
  "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
  "salaire": {"min": 0, "max": 0, "confiance": "", "analyse": ""},
  "competences": {"match": [], "manquant": []},
  "analyse": {"verdict": "", "points_forts": [], "points_faibles": []},
  "historique": [{"titre": "", "entreprise": "", "duree": "", "resume_synthetique": ""}],
  "entretien": [{"theme": "", "question": "", "attendu": ""}]
}
"""

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_with_retry(job: str, cv: str, criteria: str, file_id: str, temp: float = 0.1, retries: int = 2) -> Optional[Dict[str, Any]]:
    client = get_client()
    if not client:
        return None

    # On tronque pour maîtriser le coût
    job_c = job[:2000]
    cv_c = cv[:4000]

    user_prompt = f"""
ID: {file_id}
{SCORING_PROMPT}

OFFRE:\n{job_c}\n\nCRITERES CRITIQUES:\n{criteria}\n\nCV:\n{cv_c}
"""

    last_err = None
    for _ in range(retries + 1):
        try:
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
                temperature=temp,
                max_tokens=2200,
            )
            raw = json.loads(res.choices[0].message.content)
            return normalize_json(raw)
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    st.warning(f"⚠️ Échec analyse: {last_err}")
    return None


# -----------------------------
# 4. PERSISTENCE (facultatif)
# -----------------------------

def save_to_sheets(data: Dict[str, Any], job_desc: str) -> None:
    if not (gspread and ServiceAccountCredentials):
        return
    try:
        svc = st.secrets.get("gcp_service_account")
        if not svc:
            return
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(svc), scope)
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        i, s = data["infos"], data["scores"]
        sheet.append_row([
            dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            i.get("nom", ""), f"{s.get('global', 0)}%", i.get("email", ""), i.get("linkedin", ""), _clean_text(job_desc)[:80],
        ])
    except Exception as e:
        st.info(f"ℹ️ Sheets non accessible: {e}")


def export_to_excel(results: List[Dict[str, Any]]) -> bytes:
    flat = []
    for r in results:
        i, s, sal = r["infos"], r["scores"], r["salaire"]
        comp = r.get("competences", {})
        flat.append({
            "Nom": i.get("nom", ""),
            "Email": i.get("email", ""),
            "Tel": i.get("tel", ""),
            "Ville": i.get("ville", ""),
            "LinkedIn": i.get("linkedin", ""),
            "Poste Actuel": i.get("poste_actuel", ""),
            "Score Global": s.get("global", 0),
            "Score Tech": s.get("tech", 0),
            "Score Exp": s.get("experience", 0),
            "Score Soft": s.get("soft", 0),
            "Score Fit": s.get("fit", 0),
            "Salaire Min": sal.get("min", 0),
            "Salaire Max": sal.get("max", 0),
            "Verdict": r.get("analyse", {}).get("verdict", ""),
            "Compétences Match": ", ".join(comp.get("match", [])),
            "Compétences Manquantes": ", ".join(comp.get("manquant", [])),
        })
    df = pd.DataFrame(flat)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Candidats")
    return out.getvalue()


# -----------------------------
# 5. SIDEBAR (CONFIG)
# -----------------------------

with st.sidebar:
    st.header("⚙️ Configuration")

    # Offre
    ao_file = st.file_uploader("1️⃣ Offre d'emploi (PDF)", type="pdf", key="ao")
    ao_text = st.text_area("Ou coller le texte", height=100, placeholder="Description du poste…")
    job_text = ""
    if ao_file:
        job_text = extract_pdf_safe(ao_file.getvalue()) or ""
    elif ao_text:
        job_text = ao_text

    # Critères
    criteria = st.text_area("2️⃣ Critères Non‑Négociables", height=80, placeholder="Ex: Anglais courant, Python expert, 5+ ans…")

    # Pondérations
    st.subheader("⚖️ Pondérations")
    w_tech = st.slider("Tech %", 0, 100, 40)
    w_exp = st.slider("Expérience %", 0, 100, 30)
    w_soft = st.slider("Soft %", 0, 100, 15)
    w_fit = st.slider("Fit %", 0, 100, 15)
    total_w = w_tech + w_exp + w_soft + w_fit
    if total_w != 100:
        st.warning(f"Les pondérations totalisent {total_w}%. Elles seront normalisées.")

    # CVs
    cv_files = st.file_uploader("3️⃣ CVs Candidats (PDF)", type="pdf", accept_multiple_files=True)

    # Options
    st.subheader("🔒 Options")
    anonymize = st.checkbox("Anonymiser l'affichage (PII masquées)", value=False)
    dedupe_on = st.checkbox("Dédoublonner par email/téléphone", value=True)
    max_workers = st.number_input("Concurrence (threads)", min_value=1, max_value=8, value=3, step=1)
    qualify_threshold = st.slider("Seuil qualifié (Score ≥)", 0, 100, 70)

    # Debug
    debug_mode = st.checkbox("Mode debug (afficher JSON et erreurs)", value=False)
    st.session_state["debug"] = debug_mode

    st.divider()
    col_btn1, col_btn2 = st.columns(2)
    launch_btn = col_btn1.button("🚀 Analyser", type="primary", use_container_width=True)
    reset_btn = col_btn2.button("🗑️ Reset", use_container_width=True)

    if reset_btn:
        st.session_state.clear()
        st.rerun()

    with st.expander("ℹ️ Aide"):
        st.caption("""
        **Scoring** (par défaut): Tech 40% • Exp 30% • Soft 15% • Fit 15% — ajustables ci‑dessus.
        **Seuils**: 80+ Excellent | 60–79 Bon | 40–59 Moyen | <40 Inadéquat.
        **Conseil**: Des critères précis → IA plus sévère.
        """)

# State init
if "results" not in st.session_state:
    st.session_state["results"] = []
if "raw_store" not in st.session_state:
    st.session_state["raw_store"] = {}


# -----------------------------
# 6. LOGIQUE PRINCIPALE
# -----------------------------

def _normalize_weights(t: Tuple[int, int, int, int]) -> Tuple[float, float, float, float]:
    s = sum(t)
    if s <= 0:
        return (0.4, 0.3, 0.15, 0.15)
    return tuple(x / s for x in t)  # type: ignore


def recompute_global(score: Dict[str, int], weights: Tuple[float, float, float, float]) -> int:
    tech, exp, soft, fit = score.get("tech", 0), score.get("experience", 0), score.get("soft", 0), score.get("fit", 0)
    g = tech * weights[0] + exp * weights[1] + soft * weights[2] + fit * weights[3]
    return int(round(g))


def process_single_cv(file_obj, job_text: str, criteria: str, weights: Tuple[float, float, float, float]) -> Optional[Dict[str, Any]]:
    file_bytes = file_obj.getvalue()
    cv_text = extract_pdf_safe(file_bytes) or ""
    if len(cv_text) < 50:
        st.warning(f"⚠️ {file_obj.name}: contenu insuffisant.")
        return None
    file_id = str(uuid.uuid4())
    data = analyze_with_retry(job_text, cv_text, criteria, file_id=file_id)
    if not data:
        return None
    # Recalcule GLOBAL selon pondérations courantes (si différente du prompt)
    data["scores"]["global"] = recompute_global(data["scores"], weights)
    return data


if launch_btn:
    if not job_text or len(job_text) < 50:
        st.error("⚠️ L'offre doit contenir au moins 50 caractères.")
    elif not cv_files:
        st.error("⚠️ Ajoutez au moins un CV.")
    else:
        results: List[Dict[str, Any]] = []
        weights = _normalize_weights((w_tech, w_exp, w_soft, w_fit))

        progress = st.empty()
        bar = st.progress(0)

        futures = []
        with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
            for f in cv_files:
                futures.append(ex.submit(process_single_cv, f, job_text, criteria, weights))

            done = 0
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    # Dédoublonnage
                    if dedupe_on:
                        identity = hash_identity(res["infos"].get("email", ""), res["infos"].get("tel", ""))
                        if identity in st.session_state["raw_store"]:
                            # garde le meilleur score
                            prev = st.session_state["raw_store"][identity]
                            if res["scores"]["global"] > prev["scores"]["global"]:
                                st.session_state["raw_store"][identity] = res
                        else:
                            st.session_state["raw_store"][identity] = res
                    else:
                        results.append(res)
                done += 1
                bar.progress(done / len(futures))
                progress.text(f"📄 {done}/{len(futures)} CV traités…")

        progress.empty(); bar.empty()

        # Consolidation si dedupe
        if dedupe_on:
            results = list(st.session_state["raw_store"].values())

        # Sauvegarde optionnelle Sheets
        for d in results:
            save_to_sheets(d, job_text)

        st.session_state["results"] = results
        if results:
            st.success(f"✅ {len(results)} candidat(s) analysé(s) !")
            st.rerun()
        else:
            st.error("❌ Aucune analyse n'a abouti. Vérifiez vos PDF.")


# -----------------------------
# 7. VUES (DASHBOARD + COMPARAISON)
# -----------------------------

results: List[Dict[str, Any]] = st.session_state.get("results", []) or []

if not results:
    st.markdown(
        """
        <div style="text-align:center; padding:80px 20px;">
            <h1 style="color:var(--text-main); font-weight:800;">AI Recruiter PRO v15</h1>
            <p style="color:var(--text-sub); font-size:1.1rem;">Analyse intelligente de candidatures</p>
            <div style="margin-top:50px; opacity:0.6;">👈 Configurez dans la barre latérale pour commencer</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    # Tri et métriques
    results_sorted = sorted(results, key=lambda x: x["scores"]["global"], reverse=True)
    avg = int(round(sum(r["scores"]["global"] for r in results_sorted) / max(1, len(results_sorted))))
    top = results_sorted[0]["scores"]["global"]
    qualified_count = len([x for x in results_sorted if x["scores"]["global"] >= qualify_threshold])

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""<div class=\"kpi-card primary\"><div class=\"kpi-val\">{len(results_sorted)}</div><div class=\"kpi-label\">Candidats</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class=\"kpi-card success\"><div class=\"kpi-val\">{qualified_count}</div><div class=\"kpi-label\">Qualifiés (≥ {qualify_threshold}%)</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class=\"kpi-card warning\"><div class=\"kpi-val\">{avg}%</div><div class=\"kpi-label\">Score moyen</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class=\"kpi-card primary\"><div class=\"kpi-val\">{top}%</div><div class=\"kpi-label\">Top candidat</div></div>""", unsafe_allow_html=True)

    # Barre d'actions
    st.write("")
    left, mid, right = st.columns([2, 1, 2])
    with left:
        filter_val = st.selectbox(
            "Filtrer par score",
            options=[0, 40, 60, 70, 80],
            format_func=lambda x: "Tous" if x == 0 else f"Score ≥ {x}%",
        )
    with mid:
        if st.button("📥 Exporter Excel", use_container_width=True):
            excel_data = export_to_excel(results_sorted)
            st.download_button(
                "💾 Télécharger",
                data=excel_data,
                file_name=f"candidats_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with right:
        # Comparateur rapide
        names = [r["infos"].get("nom", f"Candidat {i+1}") for i, r in enumerate(results_sorted)]
        try:
            comp_sel = st.multiselect("Comparer (max 3)", options=names, default=names[:0], max_selections=3)
        except TypeError:
            # fallback pour versions Streamlit sans max_selections
            comp_sel = st.multiselect("Comparer", options=names, default=names[:0])

    st.divider()

    # Vue Comparaison si sélection
    if comp_sel:
        sel = [r for r in results_sorted if r["infos"].get("nom", "") in comp_sel]
        if sel:
            cols = st.columns(len(sel))
            for j, d in enumerate(sel):
                i, s = d["infos"], d["scores"]
                i_disp = anonymize_infos(i) if st.session_state.get("anonymize_override", False) else (anonymize_infos(i) if anonymize else i)
                cols[j].markdown(f"**{i_disp.get('nom', 'Candidat')} — {s.get('global',0)}%**")
                # Radar
                cat = ['Tech', 'Exp', 'Soft', 'Fit', 'Tech']
                val = [s.get('tech',0), s.get('experience',0), s.get('soft',0), s.get('fit',0), s.get('tech',0)]
                fig = go.Figure(go.Scatterpolar(r=val, theta=cat, fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=260, margin=dict(t=10,b=10,l=10,r=10))
                cols[j].plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.divider()

    # Filtrage liste
    filtered = [r for r in results_sorted if r["scores"]["global"] >= filter_val]
    if not filtered:
        st.warning(f"Aucun candidat avec un score ≥ {filter_val}%")

    # Listing candidats
    for idx, d in enumerate(filtered):
        i = d["infos"]
        s = d["scores"]
        i_disp = anonymize_infos(i) if anonymize else i

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
st.markdown(
    f"""**{h.get('titre','')}** @ {h.get('entreprise','')} — {h.get('duree','')}
> _{h.get('resume_synthetique','')}_"""
)


> _{h.get('resume_synthetique','')}_"
                            )
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

            except Exception as e:
                st.error(f"Affichage de la fiche impossible : {e}")
                if st.session_state.get("debug"):
                    st.exception(e)
            
            # Skills
            st.markdown("#### 🛠️ Compétences Techniques")
            comp = d.get("competences", {})
            skills_html = "".join([f"<span class='skill-tag match'>✓ {sk}</span>" for sk in comp.get("match", [])])
            skills_html += "".join([f"<span class='skill-tag missing'>{sk}</span>" for sk in comp.get("manquant", [])])
            st.markdown(skills_html, unsafe_allow_html=True)

            # Notes + Guide entretien
            with st.expander("🗒️ Notes & suivi"):
                note_key = f"note_{idx}"
                note_val = st.session_state.get(note_key, "")
                new_note = st.text_area("Vos notes (local, non partagé)", value=note_val, key=note_key)
                st.caption("Astuce : utilisez les notes pour consigner feedbacks d'entretien, objections, etc.")

            with st.expander("🎯 Guide d'entretien"):
                for q in d.get("entretien", [])[:6]:
                    theme = q.get("theme", "Général")
                    st.markdown(f"**{theme}** — {q.get('question','')}

> Attendu : _{q.get('attendu','')}_")
            
            if st.session_state.get("debug"):
                st.caption("FIN DE FICHE — DEBUG")
                st.json(d)


