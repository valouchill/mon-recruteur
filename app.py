# AI Recruiter PRO — v17 (Evidence-Based Scoring)
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
from pydantic import BaseModel, Field, ValidationError, conint

# API Clients
import openai
from pypdf import PdfReader

# -----------------------------
# 0. CONFIGURATION PAGE
# -----------------------------
st.set_page_config(page_title="AI Recruiter PRO v17", layout="wide", page_icon="🛡️", initial_sidebar_state="expanded")

st.markdown("""
<style>
    :root {
        --primary:#2563eb; --bg-app:#f8fafc; --text-main:#0f172a; --border:#cbd5e1;
        --score-good:#16a34a; --score-mid:#d97706; --score-bad:#dc2626;
    }
    .stApp { background: var(--bg-app); color: var(--text-main); font-family: 'Inter', sans-serif; }
    
    /* CARDS & LAYOUT */
    .candidate-card { background: white; border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); }
    .header-flex { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #f1f5f9; padding-bottom: 15px; margin-bottom: 15px; }
    
    /* TYPOGRAPHY */
    h1, h2, h3 { color: #1e293b !important; font-weight: 700; }
    .name-title { font-size: 1.4rem; font-weight: 800; color: #1e293b; margin: 0; }
    .job-subtitle { font-size: 0.95rem; color: #64748b; margin-top: 4px; }
    .section-header { font-size: 0.85rem; text-transform: uppercase; color: #94a3b8; font-weight: 700; margin-bottom: 10px; letter-spacing: 0.5px; }

    /* SCORE BADGE */
    .score-badge { 
        font-size: 1.5rem; font-weight: 900; color: white; 
        width: 60px; height: 60px; border-radius: 12px; 
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .sc-good { background: linear-gradient(135deg, #16a34a, #15803d); }
    .sc-mid { background: linear-gradient(135deg, #d97706, #b45309); }
    .sc-bad { background: linear-gradient(135deg, #dc2626, #b91c1c); }

    /* EVIDENCE BOXES */
    .evidence-box { background: #f8fafc; border-left: 3px solid #cbd5e1; padding: 10px 15px; margin-bottom: 8px; border-radius: 0 6px 6px 0; }
    .ev-skill { font-weight: 700; color: #334155; font-size: 0.9rem; }
    .ev-proof { font-size: 0.85rem; color: #475569; font-style: italic; margin-top: 2px; }
    .ev-missing { border-left-color: #ef4444; background: #fef2f2; }
    .ev-missing .ev-skill { color: #991b1b; }

    /* TAGS */
    .tag { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-right: 5px; margin-bottom: 5px; }
    .tag-blue { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
    .tag-gray { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }

    /* INPUTS FIX */
    .stTextArea textarea, .stTextInput input { background-color: white !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; }
    [data-testid="stFileUploader"] section { background: white !important; border: 1px dashed #cbd5e1 !important; }
    div[data-testid="stExpander"] { border: 1px solid #e2e8f0 !important; border-radius: 8px !important; background: white !important; box-shadow: none !important;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# 1. SCHÉMAS DE DONNÉES (STRICT)
# -----------------------------
class Infos(BaseModel):
    nom: str = "Candidat Inconnu"; email: str = "N/A"; tel: str = "N/A"; ville: str = ""; linkedin: str = ""; poste_actuel: str = ""

class Scores(BaseModel):
    global_: int = Field(0, alias="global")
    tech: int = 0; experience: int = 0; fit: int = 0

class Preuve(BaseModel):
    skill: str; preuve: str; niveau: str # Niveau: Faible, Bon, Expert

class Competences(BaseModel):
    match_details: List[Preuve] = [] # Liste des preuves
    manquant_critique: List[str] = [] # Dealbreakers
    manquant_secondaire: List[str] = []

class Analyse(BaseModel):
    verdict_auditeur: str = "Analyse en attente"; red_flags: List[str] = []

class HistoriqueItem(BaseModel):
    titre: str; entreprise: str; duree: str; contexte: str

class QuestionItem(BaseModel):
    cible: str; question: str; reponse_attendue: str

class CandidateData(BaseModel):
    infos: Infos = Infos()
    scores: Scores = Scores()
    analyse: Analyse = Analyse()
    competences: Competences = Competences()
    historique: List[HistoriqueItem] = []
    entretien: List[QuestionItem] = []

DEFAULT_DATA = CandidateData().dict(by_alias=True)

# -----------------------------
# 2. FONCTIONS UTILITAIRES
# -----------------------------
@st.cache_resource(show_spinner=False)
def get_client() -> Optional[openai.OpenAI]:
    try:
        if "GROQ_API_KEY" in st.secrets:
            return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"], timeout=45.0)
        return None
    except: return None

def clean_pdf_text(text: str) -> str:
    # Nettoyage des caractères bizarres issus du PDF
    text = re.sub(r'\s+', ' ', text) # Espaces multiples
    text = re.sub(r'[^\w\s@.+:/-]', '', text) # Caractères non-alphanumériques (sauf ponctuation basique)
    return text[:6000] # On coupe pour éviter de saturer le contexte

def extract_pdf_safe(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return clean_pdf_text(text)
    except: return ""

def normalize_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return CandidateData.parse_obj(raw).dict(by_alias=True)
    except ValidationError:
        return deepcopy(DEFAULT_DATA)

# -----------------------------
# 3. LE COEUR : L'AUDITEUR (PROMPT)
# -----------------------------
AUDITOR_PROMPT = """
ROLE: Auditeur de Recrutement Impitoyable.
TACHE: Vérifier factuellement l'adéquation CV vs OFFRE.
PRINCIPE: "Pas écrit = Pas acquis". Ne jamais supposer. Si un doute existe, c'est une absence.

RÈGLES DE SCORING (DÉTERMINISTE):
1. SCORE GLOBAL (0-100) :
   - Départ à 100 points.
   - Moins 20 points par compétence CRITIQUE manquante.
   - Moins 5 points par compétence SECONDAIRE manquante.
   - Moins 10 points si l'expérience est insuffisante (années ou secteur).
   - Moins 15 points si un RED FLAG est détecté (trous inexpliqués, job hopping excessif, fautes graves).
   - Plancher à 0.

2. PREUVES (CRUCIAL) :
   - Pour chaque compétence "matchée", tu DOIS extraire une CITATION ou un CONTEXTE précis du CV.
   - Exemple: Skill "Python" -> Preuve: "A développé une API Django chez Thales (3 ans)".
   - Si tu ne trouves pas de preuve explicite, classe-le dans "manquant".

3. STRUCTURE JSON REQUISE :
{
    "infos": { "nom": "Nom complet", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." },
    "scores": { "global": int, "tech": int (0-10), "experience": int (0-10), "fit": int (0-10) },
    "competences": {
        "match_details": [ {"skill": "Nom Skill", "preuve": "Citation du CV prouvant la skill", "niveau": "Expert/Confirmé/Junior"} ],
        "manquant_critique": ["Skill A", "Skill B"],
        "manquant_secondaire": ["Skill C"]
    },
    "analyse": {
        "verdict_auditeur": "Phrase de synthèse factuelle et tranchante.",
        "red_flags": ["Flag 1", "Flag 2"]
    },
    "historique": [ {"titre": "...", "entreprise": "...", "duree": "...", "contexte": "Secteur/Taille"} ],
    "entretien": [ {"cible": "Lacune identifiée", "question": "Question piège pour vérifier", "reponse_attendue": "..."} ]
}
"""

def audit_candidate(job: str, cv: str, criteria: str, file_id: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    if not client: return None
    
    user_prompt = f"ID_DOSSIER: {file_id}\n\n--- OFFRE ---\n{job[:2500]}\n\n--- CRITERES IMPERATIFS ---\n{criteria}\n\n--- CV CANDIDAT ---\n{cv[:4000]}"
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": AUDITOR_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0 # Zéro créativité, 100% factuel
        )
        return normalize_json(json.loads(res.choices[0].message.content))
    except Exception as e:
        print(f"Err: {e}")
        return None

def save_result(data, job_title):
    if "gcp_service_account" in st.secrets:
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            row = [
                dt.datetime.now().strftime("%Y-%m-%d"),
                data['infos']['nom'],
                data['scores']['global'],
                data['analyse']['verdict_auditeur'],
                ", ".join(data['competences']['manquant_critique'])
            ]
            sheet.append_row(row)
        except: pass

# -----------------------------
# 4. INTERFACE UTILISATEUR
# -----------------------------

# SIDEBAR
with st.sidebar:
    st.title("🛡️ Paramètres Audit")
    ao_file = st.file_uploader("1. Fiche de Poste (PDF)", type="pdf", key="ao")
    ao_txt = st.text_area("Ou texte brut", height=100)
    
    job_content = ""
    if ao_file: 
        ao_file.seek(0)
        job_content = extract_pdf_safe(ao_file.getvalue())
    elif ao_txt:
        job_content = ao_txt
        
    criteria = st.text_area("2. Critères éliminatoires (Dealbreakers)", height=100, placeholder="Ex: Anglais C1 obligatoire, Expérience management > 3 ans...")
    
    cv_files = st.file_uploader("3. Dossiers Candidats (PDF)", type="pdf", accept_multiple_files=True)
    
    c1, c2 = st.columns(2)
    launch = c1.button("Lancer l'Audit", type="primary")
    reset = c2.button("Reset")
    
    if reset:
        st.session_state.results = []
        st.rerun()

if "results" not in st.session_state: st.session_state.results = []

# LOGIQUE
if launch:
    if not job_content or len(job_content) < 50:
        st.error("⚠️ La fiche de poste est vide ou illisible.")
    elif not cv_files:
        st.error("⚠️ Aucun CV chargé.")
    else:
        res_buffer = []
        bar = st.progress(0)
        
        for i, f in enumerate(cv_files):
            f.seek(0)
            txt = extract_pdf_safe(f.read())
            if len(txt) > 50:
                data = audit_candidate(job_content, txt, criteria, str(uuid.uuid4()))
                if data:
                    save_result(data, "Job Audit")
                    res_buffer.append(data)
            bar.progress((i+1)/len(cv_files))
            
        st.session_state.results = res_buffer
        bar.empty()
        st.rerun()

# AFFICHAGE
if not st.session_state.results:
    st.info("👈 Veuillez charger une offre et des CVs pour démarrer l'audit de fiabilité.")
else:
    # Tri : Les meilleurs scores en premier
    sorted_results = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    
    # KPIs
    avg = int(statistics.mean([r['scores']['global'] for r in sorted_results]))
    qualified = len([r for r in sorted_results if r['scores']['global'] >= 70])
    
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='kpi-card'><div class='kpi-val'>{len(sorted_results)}</div><div class='kpi-label'>Audits Réalisés</div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi-card'><div class='kpi-val'>{avg}/100</div><div class='kpi-label'>Score Moyen</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi-card'><div class='kpi-val' style='color:var(--score-good)'>{qualified}</div><div class='kpi-label'>Profils Validés</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi-card'><div class='kpi-val'>{sorted_results[0]['scores']['global']}</div><div class='kpi-label'>Top Score</div></div>", unsafe_allow_html=True)
    
    st.write("---")
    
    for idx, d in enumerate(sorted_results):
        score = d['scores']['global']
        
        # Code couleur score
        if score >= 70: s_cls = "sc-good"
        elif score >= 50: s_cls = "sc-mid"
        else: s_cls = "sc-bad"
        
        # Clé unique obligatoire pour éviter les bugs d'affichage
        expander_key = f"exp_{idx}_{d['infos']['nom']}"
        
        with st.expander(f"{d['infos']['nom']} — Score Audit : {score}/100", expanded=(idx==0)):
            
            # EN-TÊTE
            c_main, c_score = st.columns([4, 1])
            with c_main:
                st.markdown(f"<div class='name-title'>{d['infos']['nom']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='job-subtitle'>{d['infos']['poste_actuel']} • {d['infos']['ville']}</div>", unsafe_allow_html=True)
                st.markdown(f"""
                <div style='margin-top:10px;'>
                    <span class='tag tag-blue'>✉️ {d['infos']['email']}</span>
                    <span class='tag tag-blue'>📱 {d['infos']['tel']}</span>
                    <span class='tag tag-blue'><a href='{d['infos']['linkedin']}' target='_blank' style='text-decoration:none; color:inherit;'>LinkedIn</a></span>
                </div>
                """, unsafe_allow_html=True)
                
                # VERDICT AUDITEUR
                if d['analyse']['red_flags']:
                    for flag in d['analyse']['red_flags']:
                        st.error(f"🚩 ALERTE : {flag}")
                
                st.info(f"💡 **Verdict Auditeur :** {d['analyse']['verdict_auditeur']}")

            with c_score:
                st.markdown(f"<div class='score-badge {s_cls}'>{score}</div>", unsafe_allow_html=True)
                st.caption("Score de Fiabilité")

            st.divider()
            
            # COLONNES PREUVES VS MANQUES
            col_match, col_miss = st.columns(2)
            
            with col_match:
                st.markdown("<div class='section-header'>✅ Compétences Prouvées (Avec Justificatifs)</div>", unsafe_allow_html=True)
                if d['competences']['match_details']:
                    for item in d['competences']['match_details']:
                        st.markdown(f"""
                        <div class='evidence-box'>
                            <div class='ev-skill'>{item['skill']} <span style='font-weight:400; color:#64748b;'>({item['niveau']})</span></div>
                            <div class='ev-proof'>"{item['preuve']}"</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("Aucune compétence majeure prouvée.")

            with col_miss:
                st.markdown("<div class='section-header'>❌ Points Bloquants & Manquants</div>", unsafe_allow_html=True)
                # Critiques
                if d['competences']['manquant_critique']:
                    for m in d['competences']['manquant_critique']:
                        st.markdown(f"""
                        <div class='evidence-box ev-missing'>
                            <div class='ev-skill'>CRITIQUE : {m}</div>
                            <div class='ev-proof'>Absence totale détectée dans le CV.</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Secondaires
                if d['competences']['manquant_secondaire']:
                    st.markdown("**Secondaires :** " + ", ".join([f"<span style='color:#64748b'>{x}</span>" for x in d['competences']['manquant_secondaire']]), unsafe_allow_html=True)

            st.divider()
            
            # HISTORIQUE & QUESTIONS
            c_hist, c_quest = st.columns(2)
            
            with c_hist:
                st.markdown("<div class='section-header'>📅 Chronologie Auditée</div>", unsafe_allow_html=True)
                if d['historique']:
                    for h in d['historique'][:3]:
                        st.markdown(f"**{h['titre']}** chez *{h['entreprise']}*")
                        st.caption(f"{h['duree']} • {h['contexte']}")
            
            with c_quest:
                st.markdown("<div class='section-header'>🎤 Questions de Vérification</div>", unsafe_allow_html=True)
                for q in d['entretien']:
                    with st.expander(f"❓ {q['cible']}", expanded=False):
                        st.write(f"**Q:** {q['question']}")
                        st.caption(f"💡 Attendu : {q['reponse_attendue']}")
