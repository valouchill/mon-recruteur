import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import io
import re
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="AI Recruiter PRO - V9.0 Expert", layout="wide", page_icon="👔")

# --- CSS "EXPERT UI" ---
st.markdown("""
<style>
    /* Conteneur Principal Candidat */
    .candidate-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        background-color: #ffffff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    /* Barre de Contact */
    .contact-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 15px;
        background-color: #f8f9fa;
        padding: 12px 15px;
        border-radius: 8px;
        border-left: 5px solid #4f46e5;
        margin-bottom: 15px;
        font-size: 0.9rem;
        color: #374151;
        align-items: center;
    }
    .contact-item { display: flex; align-items: center; gap: 5px; }
    
    /* Badges de Compétences */
    .skill-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; margin: 2px; display: inline-block; }
    .skill-expert { background-color: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }
    .skill-inter { background-color: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
    .skill-missing { background-color: #fee2e2; color: #991b1b; border: 1px solid #fecaca; text-decoration: line-through; }
    
    /* Verdict Box */
    .verdict-box {
        background: linear-gradient(to right, #eef2ff, #ffffff);
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #6366f1;
        margin-bottom: 15px;
        color: #1e1b4b;
    }

    /* Titres de section */
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1f2937;
        margin-top: 15px;
        margin-bottom: 10px;
        border-bottom: 2px solid #f3f4f6;
        padding-bottom: 5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. CONSTANTES & NORMALISATION ---

DEFAULT_ANALYSIS = {
    "infos": {"nom": "N/A", "email": "N/A", "tel": "", "ville": "", "linkedin": "", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "culture": 0},
    "salaire": {"min": 0, "max": 0, "justif": ""},
    "historique": [],
    "competences": {"expert": [], "intermediaire": [], "manquant": []},
    "analyse": {"verdict": "Non disponible", "forces": [], "risques": []},
    "guide_entretien": {"tech": [], "soft": []}
}

def normalize_analysis(raw: dict) -> dict:
    """Sécurise le JSON pour éviter les plantages UI."""
    if not isinstance(raw, dict): raw = {}
    
    # Extraction sécurisée avec valeurs par défaut
    data = DEFAULT_ANALYSIS.copy()
    
    # Infos
    raw_infos = raw.get("infos", {})
    data["infos"] = {
        "nom": str(raw_infos.get("nom", "Candidat Inconnu")),
        "email": str(raw_infos.get("email", "N/A")),
        "tel": str(raw_infos.get("tel", "N/A")),
        "ville": str(raw_infos.get("ville", "N/A")),
        "linkedin": str(raw_infos.get("linkedin", "")),
        "poste_actuel": str(raw_infos.get("poste_actuel", ""))
    }
    
    # Scores
    raw_scores = raw.get("scores", {})
    data["scores"] = {k: int(float(raw_scores.get(k, 0))) for k in data["scores"]}
    
    # Salaire
    raw_sal = raw.get("salaire", {})
    data["salaire"] = {
        "min": int(float(raw_sal.get("min", 0))),
        "max": int(float(raw_sal.get("max", 0))),
        "justif": str(raw_sal.get("justif", ""))
    }
    
    # Listes & Dicts
    data["historique"] = raw.get("historique", []) if isinstance(raw.get("historique"), list) else []
    data["competences"] = raw.get("competences", DEFAULT_ANALYSIS["competences"])
    data["analyse"] = raw.get("analyse", DEFAULT_ANALYSIS["analyse"])
    data["guide_entretien"] = raw.get("guide_entretien", DEFAULT_ANALYSIS["guide_entretien"])
    
    return data

# --- 2. MOTEUR IA ROBUSTE ---

@st.cache_resource
def get_ai_client():
    try:
        return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None

def _strip_json(text):
    match = re.search(r"``````", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()

def safe_json_parse(text):
    try:
        return normalize_analysis(json.loads(_strip_json(text)))
    except:
        return DEFAULT_ANALYSIS.copy()

@st.cache_data(ttl=3600)
def analyze_cv(job_desc, cv_text, criteria=""):
    client = get_ai_client()
    if not client: return None
    
    prompt = f"""ANALYSE RECRUTEMENT EXPERT.
    
    OFFRE: {job_desc[:1500]}
    CRITÈRES: {criteria}
    CV: {cv_text[:3500]}
    
    Génère un JSON STRICT avec cette structure exacte :
    {{
        "infos": {{ "nom": "Nom", "email": "Email", "tel": "Tel", "ville": "Ville", "linkedin": "URL", "poste_actuel": "Titre" }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "culture": 0-100 }},
        "salaire": {{ "min": 45, "max": 55, "justif": "Basé sur l'exp et le lieu" }},
        "analyse": {{
            "verdict": "Synthèse stratégique en 2 phrases.",
            "forces": ["Force 1", "Force 2"],
            "risques": ["Risque 1", "Risque 2"]
        }},
        "competences": {{
            "expert": ["Skill A", "Skill B"],
            "intermediaire": ["Skill C"],
            "manquant": ["Skill D"]
        }},
        "historique": [
            {{ "titre": "Poste", "entreprise": "Boite", "duree": "Dates", "mission": "Résumé concis" }}
        ],
        "guide_entretien": {{
            "tech": [ {{ "q": "Question Technique ?", "a": "Réponse attendue" }} ],
            "soft": [ {{ "q": "Question Comportementale ?", "a": "Réponse attendue" }} ]
        }}
    }}
    """
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return safe_json_parse(res.choices[0].message.content)
    except: return None

# --- 3. UTILS FICHIERS ---
@st.cache_data
def extract_pdf(file_bytes):
    try:
        return "\n".join([p.extract_text() for p in PdfReader(io.BytesIO(file_bytes)).pages if p.extract_text()])
    except: return ""

def save_gsheet(data, job_desc):
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            i, s = data['infos'], data['scores']
            sheet.append_row([datetime.datetime.now().strftime("%Y-%m-%d"), i['nom'], f"{s['global']}%", i['email'], i['linkedin'], job_desc[:50]])
    except: pass

# --- 4. INTERFACE UTILISATEUR ---

if 'results' not in st.session_state: st.session_state.results = []

st.title("👔 AI Recruiter PRO - V9.0")

with st.sidebar:
    st.header("1. Configuration")
    ao_pdf = st.file_uploader("Offre (PDF)", type='pdf')
    ao_txt = st.text_area("Ou texte Offre", height=100)
    job_desc = extract_pdf(ao_pdf.getvalue()) if ao_pdf else ao_txt
    
    criteria = st.text_area("Critères Clés", height=80)
    
    st.divider()
    st.header("2. Candidats")
    cvs = st.file_uploader("CVs (PDF)", type='pdf', accept_multiple_files=True)
    
    if st.button("🚀 Lancer l'Analyse", type="primary"):
        if job_desc and cvs:
            st.session_state.analyze = True
        else:
            st.warning("Il manque l'offre ou les CVs.")
            
    if st.button("🗑️ Tout effacer"):
        st.session_state.results = []
        st.rerun()

# LOGIQUE ANALYSE
if st.session_state.get('analyze', False):
    st.session_state.analyze = False
    results = []
    bar = st.progress(0)
    
    for i, cv in enumerate(cvs):
        txt = extract_pdf(cv.getvalue())
        if txt:
            d = analyze_cv(job_desc, txt, criteria)
            if d:
                save_gsheet(d, job_desc)
                results.append(d)
        bar.progress((i+1)/len(cvs))
    
    st.session_state.results = results
    st.rerun()

# AFFICHAGE DASHBOARD
if st.session_state.results:
    # Convertir en DF pour le tri
    flat_data = []
    for r in st.session_state.results:
        flat_data.append({
            'Nom': r['infos']['nom'],
            'Score': r['scores']['global'],
            'Poste': r['infos']['poste_actuel'],
            'data': r
        })
    df = pd.DataFrame(flat_data).sort_values('Score', ascending=False)
    
    # Filtres & Export
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: st.caption(f"{len(df)} Candidats analysés")
    with c3: 
        csv = df.drop(columns=['data']).to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export CSV", csv, "analysk.csv", "text/csv")

    # --- BOUCLE D'AFFICHAGE DES DOSSIERS ---
    for idx, row in df.iterrows():
        d = row['data']
        score = row['Score']
        info = d['infos']
        
        # Couleur statut
        color = "green" if score >= 75 else "orange" if score >= 50 else "red"
        
        with st.expander(f"👤 {info['nom']}  |  {score}%  |  {info['poste_actuel']}", expanded=True if idx==0 else False):
            
            # 1. BARRE DE CONTACT (HTML/CSS)
            lnk = info['linkedin']
            linkedin_html = f'<a href="{lnk}" target="_blank" style="text-decoration:none; color:#0077b5; font-weight:bold;">🔗 LinkedIn</a>' if 'http' in lnk else '<span style="color:#999;">🔗 Pas de LinkedIn</span>'
            
            st.markdown(f"""
            <div class="contact-bar">
                <div class="contact-item">📧 {info['email']}</div>
                <div class="contact-item">📱 {info['tel']}</div>
                <div class="contact-item">📍 {info['ville']}</div>
                <div class="contact-item">💰 Est. {d['salaire']['min']}-{d['salaire']['max']} k€</div>
                <div class="contact-item">{linkedin_html}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # 2. SECTION STRATÉGIQUE (2/3 - 1/3)
            col_main, col_side = st.columns([2, 1])
            
            with col_main:
                # Verdict IA
                st.markdown(f"""<div class="verdict-box"><b>🧠 Verdict IA :</b> {d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
                
                # Forces & Risques
                c_plus, c_moins = st.columns(2)
                with c_plus:
                    st.markdown("**✅ Points Forts**")
                    for f in d['analyse']['forces']: st.success(f"+ {f}")
                with c_moins:
                    st.markdown("**⚠️ Points de Vigilance**")
                    for r in d['analyse']['risques']: st.error(f"!! {r}")
                
                # Historique (Déroulable pour gagner de la place)
                with st.expander("📅 Voir l'Historique détaillé"):
                    for h in d['historique']:
                        st.markdown(f"**{h.get('titre','')}** @ {h.get('entreprise','')}")
                        st.caption(f"{h.get('duree','')} | {h.get('mission','')}")
                        st.markdown("---")

            with col_side:
                # Radar Chart
                sc = d['scores']
                fig = go.Figure(data=go.Scatterpolar(
                    r=[sc['tech'], sc['experience'], sc['soft'], sc['culture']],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself'
                ))
                fig.update_layout(height=220, margin=dict(t=20, b=20, l=30, r=30), polar=dict(radialaxis=dict(range=[0, 100], visible=True)))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")
                
                # Compétences (Badges CSS)
                st.markdown("**Compétences Clés**")
                
                html_skills = ""
                for s in d['competences']['expert']: html_skills += f"<span class='skill-badge skill-expert'>★ {s}</span>"
                for s in d['competences']['intermediaire']: html_skills += f"<span class='skill-badge skill-inter'>{s}</span>"
                for s in d['competences']['manquant']: html_skills += f"<span class='skill-badge skill-missing'>{s}</span>"
                
                st.markdown(html_skills if html_skills else "Pas de skills spécifiques détectés.", unsafe_allow_html=True)

            # 3. GUIDE ENTRETIEN (En bas)
            st.markdown('<div class="section-title">🎤 Guide d\'Entretien</div>', unsafe_allow_html=True)
            
            tab_tech, tab_soft = st.tabs(["💻 Questions Techniques", "🤝 Questions Soft Skills"])
            
            with tab_tech:
                if d['guide_entretien']['tech']:
                    for q in d['guide_entretien']['tech']:
                        st.markdown(f"**Q:** {q['q']}")
                        st.caption(f"💡 *Attendu : {q['a']}*")
                else: st.info("Pas de questions techniques générées.")
            
            with tab_soft:
                if d['guide_entretien']['soft']:
                    for q in d['guide_entretien']['soft']:
                        st.markdown(f"**Q:** {q['q']}")
                        st.caption(f"💡 *Attendu : {q['a']}*")
                else: st.info("Pas de questions soft skills générées.")

else:
    st.info("👈 Chargez une offre et des CVs pour commencer l'analyse.")
