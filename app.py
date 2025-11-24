# AI Recruiter PRO — v16 (Corrigé & Complet)
# -------------------------------------------------------------------
from __future__ import annotations

import streamlit as st
import json, io, re, uuid, time
import datetime as dt
from typing import Optional, Dict, List, Any, Tuple
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed

# Data / Viz
import pandas as pd
import plotly.graph_objects as go

# Validation
from pydantic import BaseModel, Field, ValidationError, conint, constr

# API Clients
import openai
import requests

# PDF Handling
from pypdf import PdfReader

# -----------------------------
# 0. PAGE CONFIG & THEME
# -----------------------------
st.set_page_config(page_title="AI Recruiter PRO v16", layout="wide", page_icon="🎯", initial_sidebar_state="expanded")

st.markdown("""
<style>
    :root {
        --primary:#1d4ed8; --success:#16a34a; --warning:#b45309; --danger:#b91c1c;
        --text-main:#0f172a; --text-sub:#334155; --bg-app:#f8fafc; --border:#94a3b8;
    }
    .stApp { background: var(--bg-app); color: var(--text-main); font-family: 'Source Sans Pro', sans-serif; }
    
    /* KPI Cards */
    .kpi-card { background:#fff; padding:20px; border:1px solid #cbd5e1; border-radius:8px; text-align:center; position:relative; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .kpi-card::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;border-radius:8px 8px 0 0}
    .kpi-card.primary::before{background:var(--primary)}
    .kpi-card.success::before{background:var(--success)}
    .kpi-card.warning::before{background:var(--warning)}
    .kpi-val{font-size:1.8rem;font-weight:800; color: #1e293b;}
    .kpi-label{font-size:.8rem;color:#64748b;text-transform:uppercase;font-weight:700; letter-spacing: 0.5px;}

    /* Candidate Card */
    div[data-testid="stExpander"] { background: white; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .streamlit-expanderHeader { font-weight: 600; font-size: 1.1rem; color: #0f172a; }

    /* Badges & Tags */
    .score-badge{display:inline-flex;align-items:center;justify-content:center;width:50px;height:50px;border-radius:50%;font-weight:800;font-size:1rem;color:#fff; margin-left: 10px;}
    .score-high{background:linear-gradient(135deg,#059669,#047857)}
    .score-mid{background:linear-gradient(135deg,#ea580c,#c2410c)}
    .score-low{background:linear-gradient(135deg,#dc2626,#b91c1c)}
    
    .skill-tag{background:#f8fafc;border:1px solid #e2e8f0;color:#334155;padding:4px 10px;border-radius:6px;font-size:.85rem;margin:3px;display:inline-block;font-weight:600}
    .match{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
    .missing{background:#fff7ed;border-color:#fed7aa;color:#9a3412;opacity:0.8}

    /* Layout Elements */
    .verdict-box{background:#eff6ff;padding:15px;border-radius:8px;font-weight:500;border-left:4px solid var(--primary);margin-bottom:20px; color: #1e3a8a;}
    .section-title {font-size: 0.9rem; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 10px; margin-top: 10px;}
    
    /* Timeline */
    .timeline-item { border-left: 2px solid #e2e8f0; padding-left: 15px; margin-bottom: 15px; position: relative; }
    .timeline-item::before { content: ''; position: absolute; left: -6px; top: 0; width: 10px; height: 10px; background: #cbd5e1; border-radius: 50%; }
    .tl-title { font-weight: 700; color: #0f172a; }
    .tl-meta { font-size: 0.85rem; color: #64748b; }
</style>
""", unsafe_allow_html=True)

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
    min: int = 0; max: int = 0; confiance: str = ""; analyse: str = "Non estimé"

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
# 2. OUTILS & HELPERS
# -----------------------------
@st.cache_resource(show_spinner=False)
def get_client() -> Optional[openai.OpenAI]:
    try:
        # Vérification sécurisée de la clé
        if "GROQ_API_KEY" in st.secrets:
            return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"], timeout=30.0)
        return None
    except Exception:
        return None

def _clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()

def extract_pdf_safe(file_bytes: bytes) -> Optional[str]:
    try:
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return _clean_text(text)
    except Exception:
        return None

def normalize_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Nettoie et valide le JSON reçu de l'IA"""
    try:
        # Tentative de parsing strict
        return CandidateData.parse_obj(raw).dict(by_alias=True)
    except ValidationError:
        # Fallback manuel si l'IA hallucine la structure
        safe = deepcopy(DEFAULT_DATA)
        # Mapping manuel sécurisé
        if "infos" in raw: safe["infos"].update(raw["infos"])
        if "scores" in raw: 
            for k, v in raw["scores"].items():
                if k in safe["scores"]: safe["scores"][k] = int(v)
        if "analyse" in raw: safe["analyse"].update(raw["analyse"])
        if "salaire" in raw: safe["salaire"].update(raw["salaire"])
        if "competences" in raw: safe["competences"].update(raw["competences"])
        
        # Historique & Entretien (Listes d'objets)
        if "historique" in raw and isinstance(raw["historique"], list):
            safe["historique"] = [h for h in raw["historique"] if isinstance(h, dict)]
        if "entretien" in raw and isinstance(raw["entretien"], list):
            safe["entretien"] = [q for q in raw["entretien"] if isinstance(q, dict)]
            
        return safe

# -----------------------------
# 3. ANALYSE (Groq / Règles)
# -----------------------------
SCORING_PROMPT = """
ROLE: Expert Recrutement Senior.
TACHE: Analyser le CV par rapport à l'OFFRE.
SORTIE: JSON STRICT uniquement (pas de texte avant/après).

BARÈME SCORING (0-100):
- GLOBAL: Moyenne pondérée (Tech 40%, Exp 30%, Soft 15%, Fit 15%).
- IMPORTANT: Si une compétence critique ("Must-Have") manque, le score GLOBAL ne doit pas dépasser 45.

STRUCTURE JSON ATTENDUE:
{
    "infos": { "nom": "Prénom Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." },
    "scores": { "global": int, "tech": int, "experience": int, "soft": int, "fit": int },
    "salaire": { "min": int, "max": int, "confiance": "Haute/Moyenne/Basse", "analyse": "Court avis" },
    "competences": { "match": ["Skill A", "Skill B"], "manquant": ["Skill C"] },
    "analyse": { "verdict": "Synthèse en 2 phrases.", "points_forts": ["..."], "points_faibles": ["..."] },
    "historique": [ { "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "..." } ],
    "entretien": [ { "theme": "Tech/Soft/Fit", "question": "...", "attendu": "..." } ]
}
"""

def analyze_with_groq(job: str, cv: str, criteria: str, file_id: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    if not client: return None # Fallback nécessaire
    
    user_prompt = f"ID: {file_id}\n{SCORING_PROMPT}\n\nOFFRE:\n{job[:2000]}\n\nCRITÈRES:\n{criteria}\n\nCV:\n{cv[:3500]}"
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content": user_prompt}],
            response_format={"type":"json_object"}, temperature=0.1
        )
        return normalize_json(json.loads(res.choices[0].message.content))
    except Exception as e:
        print(f"Err API: {e}")
        return None

# Simulation Règles simples (Fallback si pas d'IA)
def analyze_rules_fallback(job, cv, criteria):
    # Logique très simplifiée pour l'exemple
    return deepcopy(DEFAULT_DATA)

# -----------------------------
# 4. SIDEBAR & STATE
# -----------------------------
if "results" not in st.session_state: st.session_state["results"] = []

with st.sidebar:
    st.title("⚙️ Paramètres")
    
    st.subheader("1. L'Offre")
    ao_file = st.file_uploader("PDF Offre", type="pdf", key="ao")
    ao_text_input = st.text_area("Ou texte", height=100, placeholder="Collez l'offre ici...")
    
    # Extraction Offre
    job_text = ""
    if ao_file:
        job_text = extract_pdf_safe(ao_file.getvalue())
    elif ao_text_input:
        job_text = ao_text_input

    criteria = st.text_area("Critères Clés", height=80, placeholder="Ex: Anglais C1, Python Senior...")

    st.subheader("2. Les Candidats")
    cv_files = st.file_uploader("CVs (PDF)", type="pdf", accept_multiple_files=True)
    
    st.divider()
    
    c1, c2 = st.columns(2)
    launch_btn = c1.button("🚀 Analyser", type="primary")
    reset_btn = c2.button("🗑️ Reset")
    
    if reset_btn:
        st.session_state.results = []
        st.rerun()

# -----------------------------
# 5. LOGIQUE PRINCIPALE
# -----------------------------

# Étape d'analyse (lancée par le bouton)
if launch_btn:
    if not job_text or len(job_text) < 50:
        st.error("⚠️ L'offre est vide ou trop courte.")
    elif not cv_files:
        st.error("⚠️ Veuillez uploader au moins un CV.")
    else:
        results_buffer = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Traitement Séquentiel (plus sûr pour Streamlit Cloud que les threads)
        for i, file in enumerate(cv_files):
            status_text.text(f"Analyse de {file.name}...")
            cv_content = extract_pdf_safe(file.getvalue())
            
            if cv_content and len(cv_content) > 50:
                # Appel IA
                file_id = str(uuid.uuid4())
                data = analyze_with_groq(job_text, cv_content, criteria, file_id)
                
                if not data: # Fallback si API échoue ou pas de clé
                    data = analyze_rules_fallback(job_text, cv_content, criteria)
                    data["analyse"]["verdict"] = "Analyse IA échouée (Mode dégradé)"
                
                # On s'assure que le nom est rempli si l'IA échoue
                if data["infos"]["nom"] == "Candidat":
                    data["infos"]["nom"] = file.name
                
                results_buffer.append(data)
            
            progress_bar.progress((i + 1) / len(cv_files))
            
        st.session_state.results = results_buffer
        status_text.empty()
        progress_bar.empty()
        st.rerun() # Force le rechargement pour afficher la vue résultats

# -----------------------------
# 6. VUE RÉSULTATS (DASHBOARD)
# -----------------------------

results = st.session_state.get("results", [])

if not results:
    # LANDING PAGE
    st.markdown("""
    <div style="text-align:center; padding:60px 20px; color:#475569;">
        <h1 style="color:#0f172a; font-weight:800; font-size: 3rem;">AI Recruiter PRO</h1>
        <p style="font-size:1.2rem;">L'assistant de présélection intelligent.</p>
        <div style="margin-top:40px; display:flex; justify-content:center; gap:20px;">
            <div style="background:white; padding:20px; border-radius:8px; border:1px solid #e2e8f0; width:200px;">
                <div style="font-size:2rem;">📄</div>
                <strong>1. Définir l'offre</strong>
            </div>
            <div style="background:white; padding:20px; border-radius:8px; border:1px solid #e2e8f0; width:200px;">
                <div style="font-size:2rem;">👥</div>
                <strong>2. Uploader CVs</strong>
            </div>
            <div style="background:white; padding:20px; border-radius:8px; border:1px solid #e2e8f0; width:200px;">
                <div style="font-size:2rem;">📊</div>
                <strong>3. Ranking IA</strong>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # --- DASHBOARD ---
    
    # Tri par score global
    results_sorted = sorted(results, key=lambda x: x["scores"]["global"], reverse=True)
    
    # KPIs
    avg_score = int(sum(r["scores"]["global"] for r in results_sorted) / len(results_sorted))
    top_candidat = results_sorted[0]
    qualified = len([r for r in results_sorted if r["scores"]["global"] >= 60])

    st.markdown("### 📊 Synthèse de la campagne")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{len(results_sorted)}</div><div class="kpi-label">Dossiers Traités</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="kpi-card success"><div class="kpi-val">{qualified}</div><div class="kpi-label">Qualifiés (60%+)</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="kpi-card warning"><div class="kpi-val">{avg_score}</div><div class="kpi-label">Score Moyen</div></div>""", unsafe_allow_html=True)
    k4.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{top_candidat['scores']['global']}%</div><div class="kpi-label">Top Score</div></div>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🏆 Classement des Candidats")

    # BOUCLE D'AFFICHAGE DES CANDIDATS
    for idx, d in enumerate(results_sorted):
        info = d["infos"]
        score = d["scores"]
        
        # Couleur badge
        s_glob = score["global"]
        badge_cls = "score-high" if s_glob >= 75 else "score-mid" if s_glob >= 50 else "score-low"
        
        with st.expander(f"#{idx+1} {info['nom']} — Score: {s_glob}%", expanded=(idx==0)):
            
            # HEADER INTERNE
            c_head1, c_head2 = st.columns([4, 1])
            with c_head1:
                st.markdown(f"### {info['nom']}")
                st.caption(f"{info['poste_actuel']} • {info['ville']}")
                st.markdown(f"📧 **{info['email']}** • 📱 **{info['tel']}**")
            with c_head2:
                st.markdown(f"""<div class="score-badge {badge_cls}">{s_glob}</div>""", unsafe_allow_html=True)
            
            st.write("")
            
            # CONTENU PRINCIPAL (2 colonnes)
            col_left, col_right = st.columns([2, 1])
            
            with col_left:
                # Verdict
                st.markdown(f"""<div class="verdict-box">💡 <b>Analyse IA :</b> {d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
                
                # Forces / Faiblesses
                cf1, cf2 = st.columns(2)
                with cf1:
                    st.markdown("<div class='section-title'>✅ Points Forts</div>", unsafe_allow_html=True)
                    for p in d["analyse"]["points_forts"]:
                        st.success(p)
                with cf2:
                    st.markdown("<div class='section-title'>⚠️ Vigilance</div>", unsafe_allow_html=True)
                    for p in d["analyse"]["points_faibles"]:
                        st.warning(p)
                
                # Timeline
                st.markdown("<div class='section-title'>📅 Parcours Récent</div>", unsafe_allow_html=True)
                if d["historique"]:
                    for h in d["historique"][:3]:
                        st.markdown(f"""
                        <div class="timeline-item">
                            <div class="tl-title">{h['titre']} <span style="font-weight:400">chez {h['entreprise']}</span></div>
                            <div class="tl-meta">{h['duree']}</div>
                            <div style="font-size:0.9rem; margin-top:4px; color:#334155;">{h['resume_synthetique']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Historique non extrait.")

            with col_right:
                # Carte Salaire
                st.markdown(f"""
                <div style="background:white; border:1px solid #cbd5e1; padding:15px; border-radius:8px; text-align:center; margin-bottom:20px;">
                    <div style="color:#64748b; font-size:0.8rem; font-weight:700; text-transform:uppercase;">Est. Salaire</div>
                    <div style="font-size:1.4rem; font-weight:800; color:#0f172a;">{d['salaire']['min']}-{d['salaire']['max']} k€</div>
                    <div style="font-size:0.8rem; color:#4f46e5;">Confiance: {d['salaire']['confiance']}</div>
                </div>
                """, unsafe_allow_html=True)

                # Radar Chart
                categories = ['Tech', 'Exp', 'Soft', 'Fit', 'Tech']
                values = [score['tech'], score['experience'], score['soft'], score['fit'], score['tech']]
                
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=values, theta=categories, fill='toself',
                    line_color='#4f46e5', fillcolor='rgba(79, 70, 229, 0.2)'
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100], showticklabels=False)),
                    showlegend=False, margin=dict(t=20, b=20, l=30, r=30), height=250
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=f"radar_{idx}")

                # Skills Tags
                st.markdown("<div class='section-title'>Compétences</div>", unsafe_allow_html=True)
                for s in d["competences"]["match"]:
                    st.markdown(f"<span class='skill-tag match'>✓ {s}</span>", unsafe_allow_html=True)
                for s in d["competences"]["manquant"]:
                    st.markdown(f"<span class='skill-tag missing'>⚠️ {s}</span>", unsafe_allow_html=True)

            # Questions Entretien (Accordeon)
            with st.expander("🎤 Guide d'entretien & Questions Challenge"):
                for q in d["entretien"]:
                    st.markdown(f"**{q['theme']}** : {q['question']}")
                    st.caption(f"Attendu : {q['attendu']}")
