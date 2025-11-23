import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import statistics
import uuid
import io

# --- 0. CONFIGURATION PAGE ---
st.set_page_config(
    page_title="AI Recruiter PRO", 
    layout="wide", 
    page_icon="🔹",
    initial_sidebar_state="expanded"
)

# --- CSS (Même style harmonisé) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root { --primary: #4f46e5; --primary-light: #e0e7ff; --text-main: #312e81; --text-sub: #64748b; --bg-app: #f8fafc; --border: #cbd5e1; }
    .stApp { background-color: var(--bg-app); font-family: 'Inter', sans-serif; color: var(--text-main); }
    h1, h2, h3, h4, .stMarkdown { color: var(--text-main) !important; font-family: 'Inter', sans-serif; }
    p, li, label, .stCaption { color: var(--text-sub) !important; }
    [data-testid="stSidebar"] { background-color: white; border-right: 1px solid var(--border); }
    [data-testid="stSidebar"] * { color: var(--text-main); }
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color: var(--text-sub) !important; }
    .stTextArea textarea, .stTextInput input { color: var(--text-main) !important; caret-color: var(--primary) !important; background-color: #f8fafc !important; border: 1px solid var(--border) !important; }
    div[data-testid="stExpander"] { background: white; border: 1px solid var(--border); border-radius: 8px; box-shadow: none !important; margin-bottom: 16px; }
    .streamlit-expanderHeader { background-color: white !important; color: var(--text-main) !important; font-weight: 600; border-bottom: 1px solid #f1f5f9; }
    .streamlit-expanderHeader:hover { color: var(--primary) !important; }
    .streamlit-expanderHeader svg { fill: var(--text-sub) !important; }
    .kpi-card { background: white; padding: 20px; border: 1px solid var(--border); border-radius: 8px; text-align: center; height: 100%; }
    .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--primary); margin-bottom: 5px; }
    .kpi-label { font-size: 0.8rem; color: var(--text-sub); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
    .header-row { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 15px; border-bottom: 1px solid #f1f5f9; margin-bottom: 20px; }
    .c-name { font-size: 1.3rem; font-weight: 700; color: var(--text-main); margin: 0; }
    .c-job { font-size: 0.95rem; color: var(--text-sub); margin-top: 2px; }
    .score-box { background: var(--primary); color: white; padding: 8px 16px; border-radius: 6px; font-weight: 700; font-size: 1rem; }
    .pill { background: #f1f5f9; border: 1px solid #e2e8f0; color: var(--text-main); padding: 5px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; margin-right: 8px; margin-top: 8px; }
    .pill a { color: var(--primary) !important; text-decoration: none; font-weight: 600; }
    .analysis-container { border: 1px solid var(--border); background-color: #f8fafc; border-radius: 6px; padding: 15px; height: 100%; }
    .analysis-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-bottom: 10px; display: block; }
    .list-item { font-size: 0.9rem; margin-bottom: 6px; display: block; color: var(--text-main); }
    .txt-success { color: #15803d; }
    .txt-danger { color: #b91c1c; }
    .verdict { background: var(--primary-light); color: var(--text-main); padding: 15px; border-radius: 6px; font-weight: 500; font-size: 0.95rem; line-height: 1.5; border: 1px solid #c7d2fe; margin-bottom: 20px; }
    .tl-item { border-left: 2px solid var(--border); padding-left: 15px; margin-bottom: 20px; padding-bottom: 5px; }
    .tl-title { font-weight: 700; color: var(--text-main); font-size: 0.95rem; }
    .tl-date { font-size: 0.75rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; margin-bottom: 5px; display: block;}
    .tl-desc { font-size: 0.9rem; color: var(--text-sub); }
    .skill-tag { background: white; border: 1px solid var(--border); color: var(--text-main); padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 500; display: inline-block; margin: 2px; }
    .skill-tag.match { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }
    .skill-tag.missing { background: #fef2f2; border-color: #fecaca; color: #991b1b; text-decoration: line-through; opacity: 0.7;}
    .salary-amount { font-size: 1.5rem; font-weight: 700; color: var(--text-main); }
    .question-box { background-color: #f1f5f9; border-left: 3px solid var(--primary); padding: 12px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }
    .q-theme { text-transform: uppercase; font-size: 0.7rem; color: var(--primary); font-weight: 700; margin-bottom: 4px; }
    .q-text { font-weight: 600; color: var(--text-main); font-size: 0.9rem; margin-bottom: 6px; }
    .q-answer { font-size: 0.85rem; color: var(--text-sub); font-style: italic; }
    [data-testid="stFileUploader"] section { background-color: #f8fafc !important; border: 1px dashed var(--border) !important; }
    [data-testid="stFileUploader"] section > div, [data-testid="stFileUploader"] section span, [data-testid="stFileUploader"] section small { color: var(--text-sub) !important; }
    [data-testid="stFileUploader"] svg { fill: var(--text-sub) !important; }
    [data-testid="stFileUploader"] button { color: var(--primary) !important; border-color: var(--primary) !important; background-color: white !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. FONCTIONS ---

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
    """Initialise et met en cache le client API Groq."""
    try: 
        if "GROQ_API_KEY" not in st.secrets:
            return None
        return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except Exception as e:
        print(f"Erreur d'initialisation du client Groq: {e}")
        return None

def extract_pdf(file_or_bytes):
    """Extrait le texte d'un objet fichier PDF ou de ses bytes."""
    try: 
        reader = PdfReader(file_or_bytes)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e: 
        print(f"Erreur lecture PDF: {e}")
        return ""

def analyze_candidate(job, cv, criteria="", file_id=""):
    """Appelle l'API Groq pour analyser le CV."""
    client = get_client()
    if not client: 
        return None
    
    # --- PROMPT AVEC HYPER-RAFFINEMENT DU SCORING ---
    prompt = f"""
    ID_ANALYSIS: {file_id}
    ROLE: Expert Recrutement & Chasseur de Têtes.
    OFFRE: {job[:1500]}
    CRITERES: {criteria}
    CV: {cv[:3000]}
    
    TACHE: Analyse critique et Scoring Détaillé.
    
    METHODOLOGIE DE SCORING (STRICT ET PONDÉRÉ):
    L'objectif est l'adéquation exacte au poste, pas la simple qualité du CV.
    
    POIDS: Le score GLOBAL est calculé par vous (IA) avec cette pondération obligatoire: 
    - SCORE TECH (40%)
    - SCORE EXPERIENCE (40%)
    - SCORE SOFT (10%)
    - SCORE FIT (10%)
    
    ÉCHELLE DE NOTATION OBLIGATOIRE: 
    - 0-30: Profil Inadéquat. Manque des prérequis **MANDATORY**s (compétences ou expérience clés). Forte pénalité si un critère dans OFFRE/CRITERES est NON négociable et manquant.
    - 31-60: Potentiel ou Junior. Correspond aux exigences **NICE-TO-HAVE** mais manque de la séniorité ou des outils cruciaux.
    - 61-80: Bon Match. Possède l'expérience nécessaire et la majorité des compétences **MANDATORY**s. Un candidat à considérer sérieusement.
    - 81-100: Excellent Match/Expert. Dépasse les attentes dans la plupart des domaines. Match presque parfait.

    - SCORE TECH (0-100): Évalue la profondeur et l'alignement des compétences techniques du CV avec l'OFFRE/CRITERES.
    - SCORE EXPERIENCE (0-100): Évalue la pertinence et la durée (nombre d'années) des rôles précédents par rapport à la séniorité exigée.
    - SCORE SOFT (0-100): Évalue les qualités comportementales (leadership, communication, autonomie).
    - SCORE FIT (0-100): Évalue l'adéquation géographique, salariale et motivationnelle.

    ÉVALUATION SALARIALE (SALAIRE):
    - Estimer la fourchette salariale annuelle brute (min-max en k€, exemple 45-55) pour le profil en se basant sur : Niveau d'Expérience, Rareté des Compétences MATCHÉES et Localisation.
    - CONFIANCE (Haute/Moyenne/Basse) : La confiance doit refléter la clarté du parcours.
    - ANALYSE : Court commentaire (max 1 ligne) justifiant l'estimation.

    QUESTIONS D'ENTRETIEN (ENTRETIEN):
    - **Générer exactement 6 questions de challenge** basées sur le CV, l'OFFRE et les CRITERES.
    - La structure doit être:
        - **2 questions** avec le "theme": "**Technique**" (pour valider les compétences clés).
        - **2 questions** avec le "theme": "**Soft Skill**" (pour évaluer le comportement et le management).
        - **2 questions** avec le "theme": "**Challenge**" ou "**Motivation**" (pour évaluer la résilience et l'ambition).
    - Pour chaque question, l'"attendu" doit indiquer brièvement la réponse idéale du candidat.

    JSON STRICT:
    {{
        "infos": {{ "nom": "Prénom Nom", "email": "...", "tel": "...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": int, "max": int, "confiance": "Haute/Moyenne/Basse", "analyse": "Court commentaire justifiant l'estimation" }},
        "competences": {{ "match": ["Skill A", "Skill B"], "manquant": ["Skill C"] }},
        "analyse": {{ "verdict": "Synthèse objective (2 lignes).", "points_forts": ["Point A"], "points_faibles": ["Point B"] }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "Action." }} ],
        "entretien": [ {{ "theme": "Challenge", "question": "Question", "attendu": "Reponse" }} ]
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
    except Exception as e:
        st.error(f"❌ Erreur API Groq lors de l'analyse du CV : {e}")
        return None

def save_to_sheets(data, job_desc):
    """Sauvegarde les résultats (omise ici pour la simplicité, mais le code reste pour l'implémentation)."""
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
    
    # Gestion sécurisée du texte offre
    job_text = ""
    if ao_file:
        ao_file.seek(0) 
        job_text = extract_pdf(ao_file)
    elif ao_text_input:
        job_text = ao_text_input
        
    criteria = st.text_area("2. Critères spécifiques", height=80)
    cv_files = st.file_uploader("3. CVs Candidats", type='pdf', accept_multiple_files=True)
    launch_btn = st.button("Lancer l'Analyse", type="primary", use_container_width=True)
    
    if st.button("Reset", use_container_width=True):
        st.session_state.results = []
        st.rerun()

# State init
if 'results' not in st.session_state: st.session_state.results = []

# --- LOGIQUE DE LANCEMENT ---
if launch_btn:
    # 1. Vérification des inputs AVANT de lancer
    if get_client() is None:
        st.error("❌ Le client API Groq n'a pas pu être initialisé. Vérifiez que la clé `GROQ_API_KEY` est bien définie dans Streamlit Secrets.")
    elif not job_text or len(job_text) < 50:
        st.error("⚠️ Veuillez ajouter une **Offre (PDF ou Texte)** valide (au moins 50 caractères) avant de lancer.")
    elif not cv_files:
        st.error("⚠️ Veuillez ajouter au moins un **CV (PDF)**.")
    else:
        # 2. Lancement si tout est OK
        res = []
        prog = st.progress(0)
        
        for i, f in enumerate(cv_files):
            f.seek(0)
            txt = extract_pdf(f)
            
            unique_id = str(uuid.uuid4())
            
            if txt and len(txt) > 50:
                d = analyze_candidate(job_text, txt, criteria, file_id=unique_id)
                if d: 
                    save_to_sheets(d, job_text)
                    res.append(d)
            else:
                st.warning(f"⚠️ Impossible de lire le texte de : {f.name} (fichier potentiellement vide ou illisible).")
                
            prog.progress((i+1)/len(cv_files))
            
        prog.empty()
        st.session_state.results = res
        st.rerun()

# --- DASHBOARD CONTENT ---
if not st.session_state.results:
    st.markdown("""
    <div style="text-align: center; padding: 60px 20px; color: var(--text-sub);">
        <h1 style="color: var(--text-main);">Bienvenue sur AI Recruiter</h1>
        <p>Interface simplifiée pour l'analyse de candidatures.</p>
        <div style="margin-top: 40px; display: inline-flex; gap: 20px;">
            <div style="border:1px solid #e2e8f0; padding:20px; border-radius:8px; width:180px; color: var(--text-main);">📂 Importez l'Offre</div>
            <div style="border:1px solid #e2e8f0; padding:20px; border-radius:8px; width:180px; color: var(--text-main);">📄 Ajoutez les CVs</div>
            <div style="border:1px solid #e2e8f0; padding:20px; border-radius:8px; width:180px; color: var(--text-main);">📊 Analysez</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # KPI TOP
    sorted_res = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    if not sorted_res:
        st.warning("Aucun résultat d'analyse n'a pu être généré. Veuillez vérifier la qualité de vos fichiers PDF.")
        st.stop()
        
    avg = int(statistics.mean([r['scores']['global'] for r in sorted_res]))
    
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"""<div class="kpi-card"><div class="kpi-val">{len(sorted_res)}</div><div class="kpi-label">Dossiers</div></div>""", unsafe_allow_html=True)
    col2.markdown(f"""<div class="kpi-card"><div class="kpi-val">{avg}%</div><div class="kpi-label">Score Moyen</div></div>""", unsafe_allow_html=True)
    col3.markdown(f"""<div class="kpi-card"><div class="kpi-val">{len([x for x in sorted_res if x['scores']['global']>=70])}</div><div class="kpi-label">Qualifiés</div></div>""", unsafe_allow_html=True)
    col4.markdown(f"""<div class="kpi-card"><div class="kpi-val">{sorted_res[0]['scores']['global']}%</div><div class="kpi-label">Top Score</div></div>""", unsafe_allow_html=True)
    
    st.write("") 

    # LISTE CANDIDATS
    for idx, d in enumerate(sorted_res):
        i = d['infos']
        s = d['scores']
        
        unique_key = f"exp_{idx}_{i['nom']}_{uuid.uuid4()}"
        
        with st.expander(f"{i['nom']}  —  {s['global']}%", expanded=(idx==0)):
            
            # HEADER
            st.markdown(f"""
            <div class="header-row">
                <div>
                    <h3 class="c-name">{i['nom']}</h3>
                    <div class="c-job">{i['poste_actuel']} • {i['ville']}</div>
                    <div style="margin-top:10px;">
                        <span class="pill">📧 <a href="mailto:{i['email']}">{i['email']}</a></span>
                        <span class="pill">📞 {i['tel']}</span>
                        <span class="pill">🔗 <a href="{i['linkedin']}" target="_blank">LinkedIn</a></span>
                    </div>
                </div>
                <div class="score-box">{s['global']}%</div>
            </div>
            """, unsafe_allow_html=True)

            # VERDICT
            st.markdown(f"""<div class="verdict">{d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
            
            # GRID ANALYSE
            c1, c2 = st.columns(2)
            with c1:
                forces_html = "".join([f"<span class='list-item'>+ {f}</span>" for f in d['analyse']['points_forts'][:4]])
                st.markdown(f"""
                <div class="analysis-container">
                    <span class="analysis-title txt-success">✅ Points Forts</span>
                    {forces_html}
                </div>
                """, unsafe_allow_html=True)
            
            with c2:
                faiblesses_html = "".join([f"<span class='list-item'>- {f}</span>" for f in d['analyse']['points_faibles'][:4]])
                st.markdown(f"""
                <div class="analysis-container">
                    <span class="analysis-title txt-danger">⚠️ Points de Vigilance</span>
                    {faiblesses_html}
                </div>
                """, unsafe_allow_html=True)
            
            st.divider()
            
            # DETAILS & DATA
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
                    <div style="font-size:0.75rem; color:var(--text-sub); text-transform:uppercase; font-weight:600;">Est. Salaire</div>
                    <div class="salary-amount">{d['salaire']['min']}-{d['salaire']['max']} k€</div>
                    <div style="font-size:0.8rem; color:var(--primary);">{d['salaire']['confiance']}</div>
                    <div style="font-size:0.7rem; color:var(--text-sub); margin-top:5px; font-style: italic;">{d['salaire']['analyse']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                cat = ['Tech (40%)', 'Exp (40%)', 'Soft (10%)', 'Fit (10%)', 'Tech (40%)']
                val = [s['tech'], s['experience'], s['soft'], s['fit'], s['tech']]
                fig = go.Figure(go.Scatterpolar(
                    r=val, theta=cat, fill='toself',
                    line_color='#4f46e5', fillcolor='rgba(79, 70, 229, 0.1)'
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, linecolor='rgba(0,0,0,0)'),
                               angularaxis=dict(tickfont=dict(size=10, color='#64748b'))),
                    showlegend=False, margin=dict(t=20, b=20, l=30, r=30), height=220,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=unique_key)
            
            # SKILLS
            st.markdown("#### Compétences")
            skills_html = ""
            for sk in d['competences']['match']:
                skills_html += f"<span class='skill-tag match'>✓ {sk}</span>"
            for sk in d['competences']['manquant']:
                skills_html += f"<span class='skill-tag missing'>{sk}</span>"
            st.markdown(skills_html, unsafe_allow_html=True)
            
            st.divider()

            # CHALLENGE QUESTIONS
            st.markdown("#### 🎯 Challenge & Entretien")
            
            q_col1, q_col2 = st.columns(2)
            for i, q in enumerate(d['entretien']):
                target_col = q_col1 if i % 2 == 0 else q_col2
                with target_col:
                    theme_color = 'var(--primary)'
                    if q.get('theme') == 'Technique':
                        theme_color = '#059669' # Vert
                    elif q.get('theme') == 'Soft Skill':
                        theme_color = '#f97316' # Orange
                    
                    st.markdown(f"""
                    <div class="question-box" style="border-left-color: {theme_color};">
                        <div class="q-theme" style="color: {theme_color};">{q.get('theme', 'Question')}</div>
                        <div class="q-text">❓ {q.get('question')}</div>
                        <div class="q-answer">💡 Attendu : {q.get('attendu')}</div>
                    </div>
                    """, unsafe_allow_html=True)
