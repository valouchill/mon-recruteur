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

# --- 0. CONFIGURATION PAGE & THÈME FORCÉ ---
st.set_page_config(
    page_title="AI Recruiter PRO - V12", 
    layout="wide", 
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

# --- CSS "NUCLEAR" LIGHT MODE & TIMELINE ---
st.markdown("""
<style>
    /* 1. VARIABLES GLOBALES FORCÉES */
    :root {
        --primary-color: #4f46e5;
        --background-color: #f8f9fc;
        --text-color: #1f2937;
        --font: 'Inter', sans-serif;
    }

    /* 2. RESET COMPLET */
    [data-testid="stAppViewContainer"] { background-color: #f8f9fc !important; color: #1f2937 !important; }
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #f0f0f0 !important; }
    [data-testid="stHeader"] { background-color: rgba(255,255,255,0) !important; }
    
    /* 3. TYPOGRAPHIE FORCÉE EN NOIR/GRIS */
    h1, h2, h3, h4, h5, h6, p, span, div, li { color: #1f2937 !important; font-family: 'Inter', sans-serif !important; }
    .stMarkdown { color: #374151 !important; }
    
    /* 4. CORRECTIFS WIDGETS */
    .stTextArea textarea, .stTextInput input { background-color: #ffffff !important; color: #1f2937 !important; border: 1px solid #e5e7eb !important; }
    
    /* 5. DESIGN SYSTEM CUSTOM */
    
    /* Conteneur Principal */
    div[data-testid="stExpander"] {
        border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
        border-radius: 12px !important;
        background-color: white !important;
        margin-bottom: 24px !important;
        overflow: hidden; /* Empêche les dépassements */
    }
    
    .streamlit-expanderHeader {
        background-color: white !important;
        color: #1f2937 !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
    }
    
    .streamlit-expanderContent {
        border-top: 1px solid #f3f4f6;
        padding-top: 20px;
    }

    /* HEADER CANDIDAT */
    .candidate-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 15px; margin-bottom: 15px; border-bottom: 1px solid #f3f4f6; }
    .candidate-info h3 { font-size: 1.4rem; font-weight: 800; margin: 0; color: #111827 !important; }
    .candidate-info p { color: #6b7280 !important; margin: 0; font-size: 0.95rem; }
    
    /* SCORE RING */
    .score-ring { width: 50px; height: 50px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 800; color: white !important; font-size: 1.1rem; }
    .bg-green { background: #10b981; border: 3px solid #d1fae5; }
    .bg-orange { background: #f59e0b; border: 3px solid #fde68a; }
    .bg-red { background: #ef4444; border: 3px solid #fecaca; }

    /* CONTACT PILLS */
    .pill { display: inline-flex; align-items: center; padding: 4px 12px; background: #f3f4f6; border-radius: 20px; font-size: 0.85rem; color: #4b5563 !important; margin-right: 8px; border: 1px solid #e5e7eb; }

    /* TIMELINE CSS (NOUVEAU) */
    .timeline-item {
        position: relative;
        padding-left: 20px;
        margin-bottom: 15px;
        border-left: 2px solid #e5e7eb;
    }
    .timeline-item:last-child { border-left: 2px solid transparent; }
    .timeline-dot {
        position: absolute;
        left: -6px;
        top: 0;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #4f46e5;
    }
    .timeline-title { font-weight: 700; font-size: 0.95rem; color: #1f2937 !important; }
    .timeline-date { font-size: 0.8rem; color: #6b7280 !important; text-transform: uppercase; margin-bottom: 4px; }
    .timeline-desc { font-size: 0.9rem; color: #4b5563 !important; line-height: 1.4; font-style: italic; background: #f9fafb; padding: 8px; border-radius: 6px; margin-top: 5px;}

    /* VERDICT & SALAIRE */
    .verdict-box { background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px; color: #1e40af !important; border-radius: 0 8px 8px 0; margin-bottom: 15px; font-size: 0.95rem; }
    .salary-box { text-align: center; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; margin-bottom: 15px; }
    .salary-val { font-weight: 800; font-size: 1.2rem; color: #111827 !important; }
    .salary-lbl { font-size: 0.75rem; color: #9ca3af !important; text-transform: uppercase; }

</style>
""", unsafe_allow_html=True)

# --- 1. LOGIQUE MÉTIER & NORMALISATION ---

DEFAULT_DATA = {
    "infos": {"nom": "Candidat", "email": "", "tel": "", "ville": "", "linkedin": "", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "", "analyse": ""},
    "analyse": {"verdict": "", "points_forts": [], "points_faibles": []},
    "competences": {"match": [], "manquant": []},
    "historique": [],
    "entretien": []
}

def normalize_json(raw):
    if not isinstance(raw, dict): raw = {}
    data = DEFAULT_DATA.copy()
    
    ri = raw.get('infos', {})
    data['infos'] = {k: str(ri.get(k, DEFAULT_DATA['infos'][k])) for k in DEFAULT_DATA['infos']}
    
    rs = raw.get('scores', {})
    data['scores'] = {k: int(rs.get(k, 0)) for k in DEFAULT_DATA['scores']}
    
    rsa = raw.get('salaire', {})
    data['salaire'] = {
        "min": int(rsa.get('min', 0)), "max": int(rsa.get('max', 0)),
        "confiance": str(rsa.get('confiance', 'Moyenne')), "analyse": str(rsa.get('analyse', ''))
    }
    
    data['competences']['match'] = raw.get('competences', {}).get('match', [])
    data['competences']['manquant'] = raw.get('competences', {}).get('manquant', [])
    data['analyse']['points_forts'] = raw.get('analyse', {}).get('points_forts', [])
    data['analyse']['points_faibles'] = raw.get('analyse', {}).get('points_faibles', [])
    data['analyse']['verdict'] = raw.get('analyse', {}).get('verdict', 'N/A')
    
    # Normalisation Historique (important pour l'UI)
    hist_raw = raw.get('historique', [])
    clean_hist = []
    for h in hist_raw:
        clean_hist.append({
            "titre": str(h.get('titre', 'Poste')),
            "entreprise": str(h.get('entreprise', '')),
            "duree": str(h.get('duree', '')),
            "resume_synthetique": str(h.get('resume_synthetique', h.get('mission', ''))) # Fallback
        })
    data['historique'] = clean_hist
    
    data['entretien'] = raw.get('entretien', [])
    return data

@st.cache_resource
def get_client():
    try: return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None

def extract_pdf(file):
    try: return "\n".join([p.extract_text() for p in PdfReader(io.BytesIO(file)).pages if p.extract_text()])
    except: return ""

@st.cache_data(ttl=3600)
def analyze_candidate(job, cv, criteria=""):
    client = get_client()
    if not client: return None
    
    prompt = f"""
    Tu es un Expert Recrutement.
    
    INPUTS:
    - OFFRE: {job[:2000]}
    - CRITÈRES: {criteria}
    - CV: {cv[:3500]}
    
    INSTRUCTION SPÉCIALE HISTORIQUE :
    Pour les 2 dernières expériences, rédige un champ "resume_synthetique" de 2 lignes MAX, résumant l'impact technique et business.
    
    JSON STRICT:
    {{
        "infos": {{ "nom": "Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": int, "max": int, "confiance": "Moy/Haute", "analyse": "..." }},
        "competences": {{ "match": ["Skill A"], "manquant": ["Skill B"] }},
        "analyse": {{ "verdict": "Avis expert", "points_forts": [], "points_faibles": [] }},
        "historique": [ 
            {{ "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "Résumé 2 lignes max." }} 
        ],
        "entretien": [ {{ "theme": "...", "question": "...", "attendu": "..." }} ]
    }}
    """
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return normalize_json(json.loads(res.choices[0].message.content))
    except: return None

def save_to_sheets(data, job_desc):
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            i, s = data['infos'], data['scores']
            sheet.append_row([datetime.datetime.now().strftime("%Y-%m-%d"), i['nom'], f"{s['global']}%", i['email'], i['linkedin'], job_desc[:50]])
    except: pass

# --- 2. INTERFACE ---

if 'results' not in st.session_state: st.session_state.results = []

with st.sidebar:
    st.markdown("### ⚙️ Paramètres")
    ao_file = st.file_uploader("1. Offre (PDF)", type='pdf')
    ao_text = st.text_area("Ou texte", height=100)
    job_text = extract_pdf(ao_file.getvalue()) if ao_file else ao_text
    
    criteria = st.text_area("Critères", height=80)
    st.divider()
    cv_files = st.file_uploader("2. CVs (PDF)", type='pdf', accept_multiple_files=True)
    
    if st.button("🚀 Analyser", type="primary", use_container_width=True):
        if job_text and cv_files: st.session_state.analyze = True
    if st.button("🗑️ Reset", use_container_width=True):
        st.session_state.results = []
        st.rerun()

st.markdown("<h2 style='text-align:center; color:#4f46e5 !important;'>AI Recruiter PRO V12</h2>", unsafe_allow_html=True)

if st.session_state.get('analyze', False):
    st.session_state.analyze = False
    res = []
    bar = st.progress(0)
    for i, f in enumerate(cv_files):
        txt = extract_pdf(f.getvalue())
        if txt:
            d = analyze_candidate(job_text, txt, criteria)
            if d: 
                save_to_sheets(d, job_text)
                res.append(d)
        bar.progress((i+1)/len(cv_files))
    st.session_state.results = res
    st.rerun()

# DASHBOARD
if st.session_state.results:
    sorted_res = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    
    for idx, d in enumerate(sorted_res):
        i = d['infos']
        s = d['scores']
        score_bg = "bg-green" if s['global'] >= 75 else "bg-orange" if s['global'] >= 50 else "bg-red"
        
        # CARTE CANDIDAT
        with st.expander(f"{i['nom']}  •  {s['global']}%", expanded=(idx == 0)):
            
            # 1. HEADER
            st.markdown(f"""
            <div class="candidate-header">
                <div class="candidate-info">
                    <h3>{i['nom']}</h3>
                    <p>{i['poste_actuel']} • {i['ville']}</p>
                </div>
                <div class="score-ring {score_bg}">{s['global']}%</div>
            </div>
            <div style="margin-bottom:20px;">
                <span class="pill">📧 {i['email']}</span>
                <span class="pill">📞 {i['tel']}</span>
                <a href="{i['linkedin']}" target="_blank" style="text-decoration:none;"><span class="pill" style="color:#4f46e5 !important; border-color:#4f46e5;">🔗 LinkedIn</span></a>
            </div>
            """, unsafe_allow_html=True)
            
            # 2. CONTENU (GRID)
            c_main, c_side = st.columns([2, 1])
            
            with c_main:
                # Verdict
                st.markdown(f"""<div class="verdict-box"><b>💡 Analyse :</b> {d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
                
                # Forces/Faiblesses
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**✅ Forces**")
                    for f in d['analyse']['points_forts'][:3]: st.markdown(f"<div style='color:#166534; margin-bottom:2px;'>+ {f}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown("**⚠️ Vigilance**")
                    for f in d['analyse']['points_faibles'][:3]: st.markdown(f"<div style='color:#991b1b; margin-bottom:2px;'>! {f}</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                
                # --- HISTORIQUE CORRIGÉ (TIMELINE HTML) ---
                st.markdown("##### 📅 Expériences Clés")
                if d['historique']:
                    timeline_html = '<div class="timeline">'
                    # On prend max les 3 dernières exp
                    for h in d['historique'][:3]:
                        timeline_html += f"""
                        <div class="timeline-item">
                            <div class="timeline-dot"></div>
                            <div class="timeline-title">{h['titre']} <span style="font-weight:400; color:#6b7280;">@ {h['entreprise']}</span></div>
                            <div class="timeline-date">{h['duree']}</div>
                            <div class="timeline-desc">{h['resume_synthetique']}</div>
                        </div>
                        """
                    timeline_html += '</div>'
                    st.markdown(timeline_html, unsafe_allow_html=True)
                else:
                    st.info("Pas d'historique détecté.")

            with c_side:
                # Salaire
                sal = d['salaire']
                st.markdown(f"""
                <div class="salary-box">
                    <div class="salary-val">{sal['min']} - {sal['max']} k€</div>
                    <div class="salary-lbl">Estimation Marché</div>
                    <div style="font-size:0.8rem; margin-top:5px; color:#6b7280;">{sal['analyse']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Radar
                fig = go.Figure(data=go.Scatterpolar(
                    r=[s['tech'], s['experience'], s['soft'], s['fit']],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself',
                    line_color='#4f46e5'
                ))
                fig.update_layout(
                    height=200, margin=dict(l=20, r=20, t=20, b=20),
                    polar=dict(radialaxis=dict(visible=False, range=[0, 100]), bgcolor='white'),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True, key=f"rad_{idx}")

                # Skills
                st.markdown("**Compétences**")
                for sk in d['competences']['match'][:4]:
                    st.markdown(f"<span style='color:#166534; background:#dcfce7; padding:2px 6px; border-radius:4px; font-size:0.8rem; font-weight:600; display:inline-block; margin:2px;'>✓ {sk}</span>", unsafe_allow_html=True)
                for sk in d['competences']['manquant'][:3]:
                    st.markdown(f"<span style='color:#991b1b; background:#fee2e2; padding:2px 6px; border-radius:4px; font-size:0.8rem; display:inline-block; margin:2px; text-decoration:line-through;'>{sk}</span>", unsafe_allow_html=True)

            # Footer Entretien
            with st.expander("🎤 Questions d'entretien"):
                for q in d['entretien']:
                    st.markdown(f"**{q.get('theme', 'Q')}** : {q.get('question')}")
                    st.caption(f"Attendu : {q.get('attendu')}")

else:
    st.info("👈 Chargez une offre et des CVs.")
