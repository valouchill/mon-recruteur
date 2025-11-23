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
import uuid

# --- 0. CONFIGURATION PAGE ---
st.set_page_config(
    page_title="AI Recruiter PRO", 
    layout="wide", 
    page_icon="🔹",
    initial_sidebar_state="expanded"
)

# --- CSS (DESIGN SYSTEM) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root { --primary: #4f46e5; --text-main: #312e81; --text-sub: #64748b; --bg-app: #f8fafc; --border: #cbd5e1; }
    .stApp { background-color: var(--bg-app); font-family: 'Inter', sans-serif; color: var(--text-main); }
    h1, h2, h3, h4, .stMarkdown { color: var(--text-main) !important; font-family: 'Inter', sans-serif; }
    p, li, label, .stCaption { color: var(--text-sub) !important; }
    [data-testid="stSidebar"] { background-color: white; border-right: 1px solid var(--border); }
    [data-testid="stExpander"] { background: white; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .streamlit-expanderHeader { background-color: white !important; color: var(--text-main) !important; font-weight: 600; }
    .kpi-card { background: white; padding: 20px; border: 1px solid var(--border); border-radius: 8px; text-align: center; height: 100%; }
    .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--primary); margin-bottom: 5px; }
    .kpi-label { font-size: 0.8rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; }
    .header-row { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 15px; border-bottom: 1px solid #f1f5f9; margin-bottom: 20px; }
    .c-name { font-size: 1.3rem; font-weight: 700; color: var(--text-main); margin: 0; }
    .score-box { background: var(--primary); color: white; padding: 8px 16px; border-radius: 6px; font-weight: 700; font-size: 1rem; }
    .pill { background: #f1f5f9; border: 1px solid #e2e8f0; color: var(--text-main); padding: 5px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 500; display: inline-flex; gap: 6px; margin-right: 8px; }
    .analysis-container { border: 1px solid var(--border); background-color: #f8fafc; border-radius: 6px; padding: 15px; height: 100%; }
    .list-item { font-size: 0.9rem; margin-bottom: 6px; display: block; color: var(--text-main); }
    .txt-success { color: #15803d; } .txt-danger { color: #b91c1c; }
    .verdict { background: #e0e7ff; color: var(--text-main); padding: 15px; border-radius: 6px; font-weight: 500; border-left: 4px solid var(--primary); margin-bottom: 20px; }
    .tl-item { border-left: 2px solid var(--border); padding-left: 15px; margin-bottom: 20px; }
    .tl-title { font-weight: 700; color: var(--text-main); font-size: 0.95rem; }
    .tl-date { font-size: 0.75rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; }
    .tl-desc { font-size: 0.9rem; color: var(--text-sub); font-style: italic; margin-top: 4px; }
    .skill-tag { background: white; border: 1px solid var(--border); padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; margin: 2px; display: inline-block; }
    .match { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }
    .missing { background: #fef2f2; border-color: #fecaca; color: #991b1b; text-decoration: line-through; opacity: 0.7;}
    .salary-amount { font-size: 1.5rem; font-weight: 700; color: var(--text-main); }
    .question-box { background-color: #f1f5f9; border-left: 3px solid var(--primary); padding: 12px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }
    .q-theme { text-transform: uppercase; font-size: 0.7rem; color: var(--primary); font-weight: 700; margin-bottom: 4px; }
    .q-text { font-weight: 600; color: var(--text-main); font-size: 0.9rem; margin-bottom: 6px; }
    .q-answer { font-size: 0.85rem; color: var(--text-sub); font-style: italic; }
</style>
""", unsafe_allow_html=True)

# --- 1. LOGIQUE MÉTIER ---

DEFAULT_DATA = {
    "infos": {"nom": "Candidat", "email": "N/A", "tel": "N/A", "ville": "", "linkedin": "#", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "", "analyse": "Non estimé"},
    "analyse": {"verdict": "En attente", "points_forts": [], "points_faibles": []},
    "competences": {"match": [], "manquant": []},
    "historique": [],
    "entretien": []
}

def normalize_json(raw):
    if not isinstance(raw, dict): raw = {}
    data = DEFAULT_DATA.copy()
    for key in DEFAULT_DATA:
        if key in raw:
            if isinstance(DEFAULT_DATA[key], dict): data[key].update(raw[key])
            else: data[key] = raw[key]
    
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

# --- CORRECTION CRITIQUE LECTURE PDF ---
def extract_pdf_from_bytes(file_bytes):
    """
    Crée un flux BytesIO frais pour chaque fichier.
    C'est ici que la duplication est évitée.
    """
    try: 
        # On crée un NOUVEL objet BytesIO à chaque appel avec les données brutes
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e: 
        print(f"Erreur lecture PDF: {e}")
        return ""

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate(job, cv, criteria="", file_id=""):
    client = get_client()
    if not client: return None
    
    # --- RETOUR DU PROMPT "EXPERT" (SCORING FIABLE) ---
    prompt = f"""
    ID_ANALYSIS: {file_id}
    ROLE: Expert Recrutement.
    OFFRE: {job[:1500]}
    CRITERES: {criteria}
    CV: {cv[:3500]}
    
    TACHE: Analyse critique.
    
    1. SCORING (Pondéré et Sévère) :
       - GLOBAL (0-100) : Moyenne pondérée de Tech (40%), Expérience (30%), Soft (15%), Fit (15%).
       - Ne donne pas 80% par défaut. Si le candidat n'a pas les mots-clés exacts de l'offre, note < 50%.
    
    2. SALAIRE :
       - Estime la fourchette (k€ brut annuel) selon l'expérience (Junior/Senior) et le lieu (Paris vs Province).
    
    3. HISTORIQUE :
       - Résume les 2 dernières expériences en 2 lignes max ("resume_synthetique").
    
    JSON STRICT:
    {{
        "infos": {{ "nom": "Prénom Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": int, "max": int, "confiance": "Haute/Basse", "analyse": "..." }},
        "competences": {{ "match": ["Skill A"], "manquant": ["Skill B"] }},
        "analyse": {{ "verdict": "Synthèse (2 lignes).", "points_forts": ["A"], "points_faibles": ["B"] }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "..." }} ],
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
    except Exception:
        return None

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

with st.sidebar:
    st.markdown("### ⚙️ Paramètres")
    ao_file = st.file_uploader("1. Offre (PDF)", type='pdf', key="ao")
    ao_text_input = st.text_area("Ou texte offre", height=100)
    
    job_text = ""
    if ao_file: 
        # Lecture immédiate des bytes pour l'AO aussi
        job_text = extract_pdf_from_bytes(ao_file.getvalue())
    elif ao_text_input: 
        job_text = ao_text_input
        
    criteria = st.text_area("2. Critères spécifiques", height=80)
    cv_files = st.file_uploader("3. CVs Candidats", type='pdf', accept_multiple_files=True)
    
    launch_btn = st.button("Lancer l'Analyse", type="primary", use_container_width=True)
    
    if st.button("Reset", use_container_width=True):
        st.session_state.results = []
        st.rerun()

if 'results' not in st.session_state: st.session_state.results = []

# --- LOGIQUE PRINCIPALE (CORRIGÉE MULTI-FICHIERS) ---
if launch_btn:
    if not job_text:
        st.error("⚠️ Veuillez ajouter une Offre.")
    elif not cv_files:
        st.error("⚠️ Veuillez ajouter des CVs.")
    else:
        new_results = []
        progress_bar = st.progress(0)
        
        for i, file_obj in enumerate(cv_files):
            # --- CORRECTION MAJEURE ICI ---
            # On lit les bytes bruts du fichier Uploader
            # Cela crée une copie en mémoire indépendante pour chaque tour de boucle
            file_bytes = file_obj.getvalue()
            
            # Extraction du texte depuis ces bytes frais
            cv_text = extract_pdf_from_bytes(file_bytes)
            
            if cv_text and len(cv_text) > 50:
                # L'ID unique permet d'éviter les conflits de cache
                unique_id = str(uuid.uuid4())
                
                data = analyze_candidate(job_text, cv_text, criteria, file_id=unique_id)
                if data: 
                    save_to_sheets(data, job_text)
                    new_results.append(data)
            
            progress_bar.progress((i + 1) / len(cv_files))
            
        progress_bar.empty()
        st.session_state.results = new_results
        st.rerun()

# --- DASHBOARD CONTENT ---
if not st.session_state.results:
    st.markdown("""
    <div style="text-align: center; padding: 60px 20px; color: var(--text-sub);">
        <h1 style="color: var(--text-main);">Bienvenue sur AI Recruiter PRO</h1>
        <p>Importez une offre et des CVs pour commencer.</p>
    </div>
    """, unsafe_allow_html=True)

else:
    sorted_res = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    avg = int(statistics.mean([r['scores']['global'] for r in sorted_res])) if sorted_res else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""<div class="kpi-card"><div class="kpi-val">{len(sorted_res)}</div><div class="kpi-label">Dossiers</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="kpi-card"><div class="kpi-val">{avg}%</div><div class="kpi-label">Moyenne</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class="kpi-card"><div class="kpi-val">{len([x for x in sorted_res if x['scores']['global']>=70])}</div><div class="kpi-label">Qualifiés</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class="kpi-card"><div class="kpi-val">{sorted_res[0]['scores']['global']}%</div><div class="kpi-label">Top Score</div></div>""", unsafe_allow_html=True)
    
    st.write("") 

    for idx, d in enumerate(sorted_res):
        i = d['infos']
        s = d['scores']
        # Clé unique pour les widgets Streamlit dans la boucle
        unique_key = f"chart_{idx}_{uuid.uuid4()}"
        
        with st.expander(f"{i['nom']}  —  {s['global']}%", expanded=(idx==0)):
            
            st.markdown(f"""
            <div class="header-row">
                <div>
                    <h3 class="c-name">{i['nom']}</h3>
                    <div class="c-job">{i['poste_actuel']} • {i['ville']}</div>
                    <div style="margin-top:10px;">
                        <span class="pill">📧 {i['email']}</span>
                        <span class="pill">📞 {i['tel']}</span>
                        <span class="pill">🔗 <a href="{i['linkedin']}" target="_blank">LinkedIn</a></span>
                    </div>
                </div>
                <div class="score-box">{s['global']}%</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""<div class="verdict">{d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
            
            gc1, gc2 = st.columns(2)
            with gc1:
                forces = "".join([f"<span class='list-item'>+ {f}</span>" for f in d['analyse']['points_forts'][:4]])
                st.markdown(f"<div class='analysis-container'><span class='analysis-title txt-success'>✅ Forces</span>{forces}</div>", unsafe_allow_html=True)
            with gc2:
                faibles = "".join([f"<span class='list-item'>- {f}</span>" for f in d['analyse']['points_faibles'][:4]])
                st.markdown(f"<div class='analysis-container'><span class='analysis-title txt-danger'>⚠️ Vigilance</span>{faibles}</div>", unsafe_allow_html=True)
            
            st.divider()
            
            col_g, col_d = st.columns([2, 1])
            with col_g:
                st.markdown("#### 📅 Parcours")
                if d['historique']:
                    tl_html = ""
                    for h in d['historique'][:3]:
                        tl_html += f"""
                        <div class="tl-item">
                            <div class="tl-date">{h['duree']}</div>
                            <div class="tl-title">{h['titre']} @ {h['entreprise']}</div>
                            <div class="tl-desc">{h['resume_synthetique']}</div>
                        </div>"""
                    st.markdown(tl_html, unsafe_allow_html=True)
                else:
                    st.caption("Non détecté")

            with col_d:
                st.markdown(f"""
                <div style="padding:15px; border:1px solid #e2e8f0; border-radius:8px; text-align:center; margin-bottom:20px; background: white;">
                    <div style="font-size:0.75rem; color:var(--text-sub); text-transform:uppercase; font-weight:600;">Salaire Est.</div>
                    <div class="salary-amount">{d['salaire']['min']}-{d['salaire']['max']} k€</div>
                    <div style="font-size:0.8rem; color:var(--primary);">{d['salaire']['confiance']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                cat = ['Tech', 'Exp', 'Soft', 'Fit', 'Tech']
                val = [s['tech'], s['experience'], s['soft'], s['fit'], s['tech']]
                fig = go.Figure(go.Scatterpolar(r=val, theta=cat, fill='toself', line_color='#4f46e5', fillcolor='rgba(79, 70, 229, 0.1)'))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, linecolor='rgba(0,0,0,0)'), angularaxis=dict(tickfont=dict(size=10, color='#64748b'))),
                    showlegend=False, margin=dict(t=20, b=20, l=30, r=30), height=220, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=unique_key)
            
            st.markdown("#### Compétences")
            skills_html = ""
            for sk in d['competences']['match']: skills_html += f"<span class='skill-tag match'>✓ {sk}</span>"
            for sk in d['competences']['manquant']: skills_html += f"<span class='skill-tag missing'>{sk}</span>"
            st.markdown(skills_html, unsafe_allow_html=True)
            
            with st.expander("🎤 Questions d'entretien"):
                for q in d['entretien']:
                    st.markdown(f"**{q.get('theme','Q')}**: {q.get('question')}")
                    st.caption(f"Attendu: {q.get('attendu')}")
