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
import statistics

# --- 0. CONFIGURATION PAGE ---
st.set_page_config(
    page_title="AI Recruiter PRO - V12.5", 
    layout="wide", 
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# --- CSS MODERNE & ÉPURÉ ---
st.markdown("""
<style>
    /* VARIABLES */
    :root {
        --primary: #6366f1; /* Indigo */
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --bg-color: #f3f4f6;
        --card-bg: #ffffff;
    }

    /* GLOBAL */
    .stApp { background-color: var(--bg-color); font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #111827 !important; font-weight: 700; }
    
    /* SIDEBAR */
    [data-testid="stSidebar"] { background-color: white; border-right: 1px solid #e5e7eb; }
    
    /* KPI CARDS (TOP DASHBOARD) */
    .kpi-card {
        background: white; padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center; border: 1px solid #e5e7eb;
    }
    .kpi-val { font-size: 1.8rem; font-weight: 800; color: var(--primary); }
    .kpi-label { font-size: 0.85rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }

    /* EXPANDER (CANDIDATE CARD) */
    .streamlit-expanderHeader {
        background-color: white; border-radius: 12px; font-weight: 600; color: #1f2937;
    }
    div[data-testid="stExpander"] {
        background: white; border-radius: 12px; border: none;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 20px;
    }
    
    /* HEADER CANDIDAT DANS L'EXPANDER */
    .header-flex { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f3f4f6; padding-bottom: 15px; margin-bottom: 15px; }
    .candidate-name { font-size: 1.4rem; font-weight: 800; color: #111827; margin: 0; }
    .candidate-sub { color: #6b7280; font-size: 0.95rem; }
    
    /* SCORE RING */
    .score-badge { 
        width: 50px; height: 50px; border-radius: 50%; 
        display: flex; align-items: center; justify-content: center; 
        font-weight: 800; color: white; font-size: 1.1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .sc-green { background: linear-gradient(135deg, #10b981, #059669); }
    .sc-orange { background: linear-gradient(135deg, #f59e0b, #d97706); }
    .sc-red { background: linear-gradient(135deg, #ef4444, #b91c1c); }

    /* PILLS & TAGS */
    .pill { 
        background: #f9fafb; padding: 6px 12px; border-radius: 20px; 
        font-size: 0.8rem; color: #374151; border: 1px solid #e5e7eb; 
        display: inline-flex; align-items: center; gap: 6px; margin-right: 8px;
    }
    
    /* ANALYSE BOX */
    .insight-box {
        background: #eff6ff; border-left: 4px solid #6366f1; 
        padding: 15px; border-radius: 0 8px 8px 0; color: #1e40af; 
        font-size: 0.95rem; line-height: 1.5; margin-bottom: 20px;
    }

    /* TIMELINE */
    .tl-container { position: relative; border-left: 2px solid #e5e7eb; margin-left: 10px; padding-left: 20px; margin-top: 10px; }
    .tl-item { position: relative; margin-bottom: 25px; }
    .tl-dot { 
        position: absolute; left: -26px; top: 0; width: 14px; height: 14px; 
        background: #6366f1; border-radius: 50%; border: 3px solid white; 
        box-shadow: 0 0 0 1px #e5e7eb; 
    }
    .tl-title { font-weight: 700; color: #1f2937; }
    .tl-date { font-size: 0.8rem; color: #6b7280; font-weight: 600; text-transform: uppercase; }
    .tl-desc { background: #f9fafb; padding: 10px; border-radius: 6px; border: 1px solid #f3f4f6; margin-top: 5px; font-size: 0.9rem; color: #4b5563; }

    /* SALARY CARD */
    .salary-card {
        background: linear-gradient(135deg, #ffffff, #f9fafb);
        border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px;
        text-align: center; margin-bottom: 20px;
    }
    .salary-amount { font-size: 1.5rem; font-weight: 800; color: #111827; }
</style>
""", unsafe_allow_html=True)

# --- 1. LOGIQUE MÉTIER ---

DEFAULT_DATA = {
    "infos": {"nom": "Candidat Inconnu", "email": "N/A", "tel": "N/A", "ville": "N/A", "linkedin": "#", "poste_actuel": "Non précisé"},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "", "analyse": "Pas d'estimation"},
    "analyse": {"verdict": "Analyse impossible", "points_forts": [], "points_faibles": []},
    "competences": {"match": [], "manquant": []},
    "historique": [],
    "entretien": []
}

def normalize_json(raw):
    if not isinstance(raw, dict): raw = {}
    data = DEFAULT_DATA.copy()
    
    # Fusion récursive simplifiée
    for key in DEFAULT_DATA:
        if key in raw:
            if isinstance(DEFAULT_DATA[key], dict):
                data[key].update(raw[key])
            else:
                data[key] = raw[key]
    
    # Nettoyage historique spécifique
    clean_hist = []
    for h in raw.get('historique', []):
        clean_hist.append({
            "titre": str(h.get('titre', 'Poste')),
            "entreprise": str(h.get('entreprise', '')),
            "duree": str(h.get('duree', '')),
            "resume_synthetique": str(h.get('resume_synthetique', h.get('mission', '')))
        })
    data['historique'] = clean_hist
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
    Rôle: Expert Recrutement Tech.
    CONTEXTE:
    - OFFRE: {job[:1500]}
    - CRITÈRES CLÉS: {criteria}
    - CV CANDIDAT: {cv[:3000]}
    
    TACHE: Analyse ce profil. Sois critique.
    
    FORMAT JSON ATTENDU (Strict):
    {{
        "infos": {{ "nom": "Prénom Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": int (k€), "max": int (k€), "confiance": "Haute/Basse", "analyse": "Court commentaire" }},
        "competences": {{ "match": ["Skill A", "Skill B"], "manquant": ["Skill C"] }},
        "analyse": {{ "verdict": "Synthèse percutante (3 lignes max).", "points_forts": [], "points_faibles": [] }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "Action + Résultat (1 phrase)" }} ],
        "entretien": [ {{ "theme": "...", "question": "...", "attendu": "..." }} ]
    }}
    """
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
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

# --- 2. INTERFACE UTILISATEUR ---

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2617/2617937.png", width=50)
    st.title("Paramètres")
    st.caption("v12.5 • Powered by Llama 3.3")
    
    st.markdown("### 1️⃣ L'Offre")
    ao_file = st.file_uploader("Fichier PDF", type='pdf', key="ao")
    ao_text_input = st.text_area("Ou coller le texte", height=100, placeholder="Description du poste...")
    
    job_text = extract_pdf(ao_file.getvalue()) if ao_file else ao_text_input
    
    with st.expander("Critères Spécifiques"):
        criteria = st.text_area("Ex: Anglais courant impératif, Expert Azure...", height=80)
    
    st.markdown("### 2️⃣ Les Candidats")
    cv_files = st.file_uploader("Upload CVs (PDF)", type='pdf', accept_multiple_files=True)
    
    launch_btn = st.button("⚡ Lancer l'Analyse", type="primary", use_container_width=True)
    
    if st.button("🔄 Nouvelle Recherche", use_container_width=True):
        st.session_state.results = []
        st.rerun()

# --- MAIN CONTENT ---

# STATE MANAGEMENT
if 'results' not in st.session_state: st.session_state.results = []

# LOGIQUE D'ANALYSE
if launch_btn and job_text and cv_files:
    res = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, f in enumerate(cv_files):
        status_text.text(f"Analyse de {f.name}...")
        txt = extract_pdf(f.getvalue())
        if txt:
            d = analyze_candidate(job_text, txt, criteria)
            if d: 
                save_to_sheets(d, job_text)
                res.append(d)
        progress_bar.progress((i+1)/len(cv_files))
    
    status_text.empty()
    progress_bar.empty()
    st.session_state.results = res
    st.rerun()

# --- DASHBOARD AFFICHAGE ---

if not st.session_state.results:
    # LANDING PAGE (ETAT VIDE)
    st.markdown("""
    <div style="text-align: center; padding: 50px 20px;">
        <h1 style="font-size: 3rem; margin-bottom: 10px;">⚡ AI Recruiter PRO</h1>
        <p style="color: #6b7280; font-size: 1.2rem;">Analysez, matchez et triez vos candidats en quelques secondes.</p>
        <div style="margin-top: 30px; display: flex; justify-content: center; gap: 20px;">
            <div style="background:white; padding:20px; border-radius:12px; box-shadow:0 4px 6px rgba(0,0,0,0.05); width:200px;">
                <div style="font-size:2rem;">📄</div>
                <div style="font-weight:600; margin-top:10px;">1. Importez l'Offre</div>
            </div>
            <div style="background:white; padding:20px; border-radius:12px; box-shadow:0 4px 6px rgba(0,0,0,0.05); width:200px;">
                <div style="font-size:2rem;">👥</div>
                <div style="font-weight:600; margin-top:10px;">2. Ajoutez les CVs</div>
            </div>
            <div style="background:white; padding:20px; border-radius:12px; box-shadow:0 4px 6px rgba(0,0,0,0.05); width:200px;">
                <div style="font-size:2rem;">📊</div>
                <div style="font-weight:600; margin-top:10px;">3. Obtenez le Ranking</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # 1. SECTION KPI (TOP OF PAGE)
    sorted_res = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    avg_score = int(statistics.mean([r['scores']['global'] for r in sorted_res]))
    top_candidate = sorted_res[0]['infos']['nom']
    
    st.markdown("### 📊 Synthèse de la campagne")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"""<div class="kpi-card"><div class="kpi-val">{len(sorted_res)}</div><div class="kpi-label">Candidats</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="kpi-card"><div class="kpi-val">{avg_score}%</div><div class="kpi-label">Score Moyen</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:#10b981;">{len([r for r in sorted_res if r['scores']['global']>70])}</div><div class="kpi-label">Top Profils</div></div>""", unsafe_allow_html=True)
    k4.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="font-size:1.2rem; line-height:2.2rem;">{top_candidate}</div><div class="kpi-label">Meilleur Match</div></div>""", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. LISTE DETAILLÉE
    st.markdown("### 👥 Détail des profils")
    
    for idx, d in enumerate(sorted_res):
        i = d['infos']
        s = d['scores']
        
        # Couleur dynamique
        color_cls = "sc-green" if s['global'] >= 75 else "sc-orange" if s['global'] >= 50 else "sc-red"
        
        with st.expander(f"#{idx+1} {i['nom']} ({s['global']}%)", expanded=(idx == 0)):
            
            # HEADER INTERNE
            st.markdown(f"""
            <div class="header-flex">
                <div>
                    <h2 class="candidate-name">{i['nom']}</h2>
                    <div class="candidate-sub">{i['poste_actuel']} • {i['ville']}</div>
                    <div style="margin-top:10px;">
                        <span class="pill">✉️ {i['email']}</span>
                        <span class="pill">📱 {i['tel']}</span>
                        <a href="{i['linkedin']}" target="_blank" style="text-decoration:none;"><span class="pill" style="color:#6366f1; border-color:#6366f1;">🔗 LinkedIn</span></a>
                    </div>
                </div>
                <div class="score-badge {color_cls}">{s['global']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # COLONNES CONTENU
            c_left, c_right = st.columns([2, 1])
            
            with c_left:
                # ANALYSE TEXTE
                st.markdown(f"""<div class="insight-box"><b>💡 L'avis de l'IA :</b><br>{d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
                
                # FORCES / FAIBLESSES
                cf1, cf2 = st.columns(2)
                with cf1:
                    st.markdown("##### ✅ Points Forts")
                    for f in d['analyse']['points_forts'][:3]: st.success(f"{f}")
                with cf2:
                    st.markdown("##### ⚠️ Points de Vigilance")
                    for f in d['analyse']['points_faibles'][:3]: st.error(f"{f}")
                
                st.markdown("##### 📅 Parcours Récent")
                if d['historique']:
                    html_tl = '<div class="tl-container">'
                    for h in d['historique'][:3]:
                        html_tl += f"""
                        <div class="tl-item">
                            <div class="tl-dot"></div>
                            <div class="tl-title">{h['titre']} <span style="font-weight:400; color:#6b7280;">@ {h['entreprise']}</span></div>
                            <div class="tl-date">{h['duree']}</div>
                            <div class="tl-desc">{h['resume_synthetique']}</div>
                        </div>
                        """
                    html_tl += "</div>"
                    st.markdown(html_tl, unsafe_allow_html=True)
            
            with c_right:
                # SALAIRE
                sal = d['salaire']
                st.markdown(f"""
                <div class="salary-card">
                    <div style="color:#6b7280; font-size:0.8rem; text-transform:uppercase; margin-bottom:5px;">Estimation Salaire</div>
                    <div class="salary-amount">{sal['min']}-{sal['max']} k€</div>
                    <div style="font-size:0.8rem; color:#6366f1; margin-top:5px;">{sal['analyse']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # RADAR CHART (PLOTLY)
                categories = ['Tech', 'Exp.', 'Soft Skills', 'Culture Fit', 'Tech']
                values = [s['tech'], s['experience'], s['soft'], s['fit'], s['tech']]
                
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=values, theta=categories, fill='toself',
                    line_color='#6366f1', fillcolor='rgba(99, 102, 241, 0.2)'
                ))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, linecolor='rgba(0,0,0,0)'),
                        angularaxis=dict(tickfont=dict(size=10, color='#6b7280'))
                    ),
                    showlegend=False,
                    margin=dict(t=20, b=20, l=30, r=30),
                    height=250,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                
                # SKILLS TAGS
                st.markdown("**Compétences Clés**")
                for sk in d['competences']['match'][:5]:
                    st.markdown(f"<span style='background:#dcfce7; color:#166534; padding:2px 8px; border-radius:10px; font-size:0.8rem; margin:2px; display:inline-block;'>✓ {sk}</span>", unsafe_allow_html=True)
            
            # FOOTER (QUESTIONS)
            with st.expander("🎤 Guide d'entretien suggéré"):
                for q in d['entretien']:
                    st.markdown(f"**Q: {q.get('question')}**")
                    st.caption(f"🎯 Attendu : {q.get('attendu')}")
