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
    page_title="AI Recruiter Maestro", 
    layout="wide", 
    page_icon="✨",
    initial_sidebar_state="expanded"
)

# --- CSS "NUCLEAR" LIGHT MODE ---
st.markdown("""
<style>
    /* 1. VARIABLES GLOBALES FORCÉES */
    :root {
        --primary-color: #4f46e5;
        --background-color: #f8f9fc;
        --secondary-background-color: #ffffff;
        --text-color: #1f2937;
        --font: 'Inter', sans-serif;
    }

    /* 2. RESET COMPLET DU BODY ET APP */
    [data-testid="stAppViewContainer"] {
        background-color: #f8f9fc !important;
        color: #1f2937 !important;
    }
    
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #f0f0f0 !important;
    }

    [data-testid="stHeader"] {
        background-color: rgba(255, 255, 255, 0) !important;
    }

    /* 3. CORRECTION DES INPUTS ET TEXT AREAS (SOUVENT SOMBRES) */
    .stTextArea textarea, .stTextInput input {
        background-color: #ffffff !important;
        color: #1f2937 !important;
        border: 1px solid #e5e7eb !important;
    }
    
    /* 4. CORRECTION DES EXPANDERS (FOND BLANC PUR) */
    .streamlit-expanderHeader {
        background-color: #ffffff !important;
        color: #1f2937 !important;
        border-radius: 8px !important;
    }
    
    .streamlit-expanderContent {
        background-color: #ffffff !important;
        color: #374151 !important;
        border-top: 1px solid #f0f0f0 !important;
    }
    
    /* 5. TYPOGRAPHIE & COULEURS DE TEXTE */
    h1, h2, h3, h4, h5, h6, p, span, div {
        color: #1f2937 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stMarkdown {
        color: #374151 !important;
    }
    
    /* --- DESIGN SYSTEM --- */

    /* CARD CONTAINER */
    div[data-testid="stExpander"] {
        border: none !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
        border-radius: 12px !important;
        background-color: white !important;
        margin-bottom: 20px !important;
    }

    /* HEADER DU CANDIDAT */
    .candidate-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 15px;
        border-bottom: 1px solid #f3f4f6;
        margin-bottom: 15px;
    }
    
    .candidate-profile {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    
    .avatar {
        width: 52px;
        height: 52px;
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: #ffffff !important; /* Blanc forcé sur l'avatar */
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 1.25rem;
    }
    
    /* SCORE BADGE */
    .score-ring {
        width: 56px;
        height: 56px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 1.1rem;
        color: #ffffff !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .score-green { background: #10b981; border: 3px solid #d1fae5; }
    .score-orange { background: #f59e0b; border: 3px solid #fde68a; }
    .score-red { background: #ef4444; border: 3px solid #fecaca; }

    /* VERDICT BOX */
    .verdict-container {
        background-color: #eff6ff !important;
        border-left: 4px solid #3b82f6 !important;
        padding: 16px;
        border-radius: 0 8px 8px 0;
        color: #1e3a8a !important;
        font-size: 0.95rem;
        margin-bottom: 20px;
    }

    /* CONTACT PILLS */
    .contact-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        background-color: #f9fafb !important;
        border-radius: 9999px;
        color: #4b5563 !important;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 8px;
        margin-bottom: 8px;
        border: 1px solid #e5e7eb !important;
    }

    /* COMPÉTENCES TAGS */
    .tag {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 2px;
    }
    .tag-expert { background: #dcfce7 !important; color: #166534 !important; border: 1px solid #bbf7d0 !important; }
    .tag-mid { background: #e0e7ff !important; color: #3730a3 !important; border: 1px solid #c7d2fe !important; }
    .tag-miss { background: #fee2e2 !important; color: #991b1b !important; text-decoration: line-through; opacity: 0.8; }

    /* SALAIRE WIDGET */
    .salary-widget {
        background: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .salary-widget::before {
        content: "";
        position: absolute;
        top: 0; left: 0; width: 100%; height: 4px;
        background: linear-gradient(90deg, #10b981, #3b82f6);
    }
    .salary-value { font-size: 1.4rem; font-weight: 800; color: #111827 !important; }
    .salary-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: #9ca3af !important; margin-top: 5px; }

    /* KPI CARD */
    .kpi-card {
        background: white !important;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #f3f4f6;
        text-align: center;
    }
    .kpi-val { font-size: 2rem; font-weight: 800; color: #111827 !important; }
    .kpi-lbl { font-size: 0.85rem; color: #6b7280 !important; text-transform: uppercase; letter-spacing: 0.5px; }

</style>
""", unsafe_allow_html=True)

# --- 1. LOGIQUE MÉTIER ---
DEFAULT_DATA = {
    "infos": {"nom": "Candidat", "email": "", "tel": "", "ville": "", "linkedin": "", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "Moyenne", "analyse": ""},
    "analyse": {"verdict": "Non analysé", "points_forts": [], "points_faibles": []},
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
    data['historique'] = raw.get('historique', [])
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
    
    salary_context = "Marché France Tech 2025: Junior 40-50k, Senior 60-80k, Lead 80k+. +15% Paris."
    
    prompt = f"""
    Tu es un Expert Recrutement UX. Analyse précise requise.
    INPUTS:
    - OFFRE: {job[:2000]}
    - CRITÈRES: {criteria}
    - CV: {cv[:3500]}
    - SALAIRE REF: {salary_context}
    
    JSON STRICT:
    {{
        "infos": {{ "nom": "Prénom Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": int, "max": int, "confiance": "Haute/Moyenne", "analyse": "Ex: Marché tendu Paris" }},
        "competences": {{ "match": ["Skill A", "Skill B"], "manquant": ["Skill C"] }},
        "analyse": {{ "verdict": "Phrase courte percutante", "points_forts": ["Force 1"], "points_faibles": ["Faible 1"] }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "mission": "..." }} ],
        "entretien": [ {{ "theme": "Tech", "question": "...", "attendu": "..." }} ]
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

# --- 2. INTERFACE PRINCIPALE ---

if 'results' not in st.session_state: st.session_state.results = []

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    ao_file = st.file_uploader("1. Offre d'emploi (PDF)", type='pdf')
    ao_text = st.text_area("Ou coller texte", height=100)
    job_text = extract_pdf(ao_file.getvalue()) if ao_file else ao_text
    
    criteria = st.text_area("Critères Clés", height=80, placeholder="Ex: Anglais, Python...")
    
    st.divider()
    cv_files = st.file_uploader("2. Candidats (PDF)", type='pdf', accept_multiple_files=True)
    
    if st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True):
        if job_text and cv_files: st.session_state.analyze = True
    
    if st.button("🔄 Reset", use_container_width=True):
        st.session_state.results = []
        st.rerun()

# Hero Section (Light Theme Forced)
st.markdown("""
<div style='text-align: center; padding-bottom: 30px;'>
    <h1 style='background: linear-gradient(to right, #4f46e5, #9333ea); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px;'>
        AI Recruiter Maestro
    </h1>
    <p style='color: #6b7280; font-size: 1.1rem;'>L'intelligence artificielle au service de votre recrutement.</p>
</div>
""", unsafe_allow_html=True)

# Logique Analyse
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

# DASHBOARD VIEW
if st.session_state.results:
    
    # KPI
    df = pd.DataFrame([r['scores']['global'] for r in st.session_state.results], columns=['Score'])
    avg_score = int(df['Score'].mean())
    top_score = int(df['Score'].max())
    count = len(df)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-lbl">Candidats</div><div class="kpi-val">{count}</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-lbl">Moyenne</div><div class="kpi-val">{avg_score}%</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-lbl">Top Score</div><div class="kpi-val">{top_score}%</div></div>""", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    sorted_results = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)

    # FEED
    for idx, d in enumerate(sorted_results):
        i = d['infos']
        s = d['scores']
        
        score_color = "score-green" if s['global'] >= 75 else "score-orange" if s['global'] >= 50 else "score-red"
        initials = "".join([n[0] for n in i['nom'].split()[:2]]).upper()
        
        with st.expander(f"{i['nom']}  •  {s['global']}%", expanded=(idx == 0)):
            
            # Header HTML
            st.markdown(f"""
            <div class="candidate-header">
                <div class="candidate-profile">
                    <div class="avatar">{initials}</div>
                    <div class="candidate-info">
                        <h3 style="color:#1f2937 !important;">{i['nom']}</h3>
                        <p style="color:#6b7280 !important;">{i['poste_actuel']} • {i['ville']}</p>
                    </div>
                </div>
                <div class="score-ring {score_color}">
                    {s['global']}%
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Contact Bar HTML
            linkedin_link = f'<a href="{i["linkedin"]}" target="_blank" style="text-decoration:none; color:#4f46e5;">🔗 LinkedIn</a>' if i['linkedin'] else '<span style="color:#ccc">🔗 No LinkedIn</span>'
            st.markdown(f"""
            <div style="margin-bottom: 20px;">
                <span class="contact-pill">📧 {i['email']}</span>
                <span class="contact-pill">📞 {i['tel']}</span>
                <span class="contact-pill">{linkedin_link}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Grid Layout
            col_main, col_side = st.columns([2, 1])
            
            with col_main:
                # Verdict
                st.markdown(f"""<div class="verdict-container"><b>💡 L'avis de l'IA :</b> {d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
                
                # Forces / Faiblesses
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**✅ POINTS FORTS**")
                    for f in d['analyse']['points_forts'][:3]: st.markdown(f"<div style='color:#166534; margin-bottom:4px;'>• {f}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown("**⚠️ VIGILANCE**")
                    for f in d['analyse']['points_faibles'][:3]: st.markdown(f"<div style='color:#991b1b; margin-bottom:4px;'>• {f}</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Historique
                st.markdown("##### 📅 Expérience Récente")
                if d['historique']:
                    for h in d['historique'][:2]:
                        st.markdown(f"**{h.get('titre','')}** | {h.get('entreprise','')}")
                        st.caption(f"{h.get('duree','')} — {h.get('mission','')}")
                else:
                    st.info("Historique non détecté.")

            with col_side:
                # Salaire HTML
                sal = d['salaire']
                st.markdown(f"""
                <div class="salary-widget">
                    <div class="salary-value">{sal['min']} - {sal['max']} k€</div>
                    <div class="salary-label">Estimation Marché</div>
                    <div style="font-size:0.8rem; color:#6b7280; margin-top:5px;">{sal['analyse']}</div>
                </div>
                <br>
                """, unsafe_allow_html=True)
                
                # Tags HTML
                st.caption("🛠️ COMPÉTENCES CLÉS")
                tags_html = ""
                for sk in d['competences']['match'][:5]:
                    tags_html += f'<span class="tag tag-expert">{sk}</span>'
                for sk in d['competences']['manquant'][:3]:
                    tags_html += f'<span class="tag tag-miss">{sk}</span>'
                st.markdown(tags_html, unsafe_allow_html=True)
                
                # Radar
                fig = go.Figure(data=go.Scatterpolar(
                    r=[s['tech'], s['experience'], s['soft'], s['fit']],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself',
                    line_color='#6366f1'
                ))
                fig.update_layout(
                    height=180, 
                    margin=dict(l=20, r=20, t=20, b=20),
                    polar=dict(radialaxis=dict(visible=False, range=[0, 100]), bgcolor='white'),
                    showlegend=False,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

            # Footer (Entretien)
            with st.expander("🎤 Voir le Guide d'Entretien"):
                for q in d['entretien']:
                    st.markdown(f"**Q ({q.get('theme','Gen')}):** {q.get('question')}")
                    st.info(f"🎯 Attendu: {q.get('attendu')}")

else:
    st.markdown("""
    <div style="text-align: center; padding: 50px; color: #9ca3af;">
        <h3>👋 Prêt à recruter ?</h3>
        <p>Utilisez la barre latérale pour charger une offre et des CVs.</p>
    </div>
    """, unsafe_allow_html=True)
