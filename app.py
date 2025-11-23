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
import time
from typing import Optional, Dict, List

# --- 0. CONFIGURATION PAGE ---
st.set_page_config(
    page_title="AI Recruiter PRO v14", 
    layout="wide", 
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

# --- CSS AMÉLIORÉ ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    :root { 
        --primary: #4f46e5; 
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --text-main: #312e81; 
        --text-sub: #64748b; 
        --bg-app: #f8fafc; 
        --border: #cbd5e1; 
    }
    
    .stApp { background-color: var(--bg-app); font-family: 'Inter', sans-serif; color: var(--text-main); }
    h1, h2, h3, h4, .stMarkdown { color: var(--text-main) !important; font-family: 'Inter', sans-serif; }
    p, li, label, .stCaption { color: var(--text-sub) !important; }
    
    [data-testid="stSidebar"] { background-color: white; border-right: 1px solid var(--border); }
    [data-testid="stExpander"] { background: white; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .streamlit-expanderHeader { background-color: white !important; color: var(--text-main) !important; font-weight: 600; }
    
    /* KPI Cards avec couleurs sémantiques */
    .kpi-card { background: white; padding: 20px; border: 1px solid var(--border); border-radius: 8px; text-align: center; height: 100%; position: relative; }
    .kpi-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px; border-radius: 8px 8px 0 0; }
    .kpi-card.primary::before { background: var(--primary); }
    .kpi-card.success::before { background: var(--success); }
    .kpi-card.warning::before { background: var(--warning); }
    .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--text-main); margin-bottom: 5px; }
    .kpi-label { font-size: 0.8rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; }
    
    /* Score visuel */
    .score-badge { display: inline-flex; align-items: center; justify-content: center; width: 60px; height: 60px; border-radius: 50%; font-weight: 800; font-size: 1.1rem; color: white; }
    .score-high { background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 4px 10px rgba(16, 185, 129, 0.3); }
    .score-mid { background: linear-gradient(135deg, #f59e0b, #d97706); box-shadow: 0 4px 10px rgba(245, 158, 11, 0.3); }
    .score-low { background: linear-gradient(135deg, #ef4444, #dc2626); box-shadow: 0 4px 10px rgba(239, 68, 68, 0.3); }
    
    .header-row { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 15px; border-bottom: 1px solid #f1f5f9; margin-bottom: 20px; }
    .c-name { font-size: 1.3rem; font-weight: 800; color: var(--text-main); margin: 0; }
    .c-job { font-size: 0.95rem; color: var(--text-sub); margin-top: 2px; }
    
    .pill { background: #f1f5f9; border: 1px solid #e2e8f0; color: var(--text-main); padding: 5px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 500; display: inline-flex; gap: 6px; margin-right: 8px; cursor: pointer; transition: all 0.2s; }
    .pill:hover { background: #e0e7ff; border-color: var(--primary); }
    .pill a { color: var(--primary) !important; text-decoration: none; font-weight: 600; }
    
    .analysis-box { border: 1px solid var(--border); background-color: #f8fafc; border-radius: 6px; padding: 15px; height: 100%; }
    .analysis-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; margin-bottom: 10px; display: block; }
    .list-item { font-size: 0.9rem; margin-bottom: 6px; display: block; color: var(--text-main); line-height: 1.4; }
    .txt-success { color: var(--success); } .txt-danger { color: var(--danger); }
    
    .verdict { background: linear-gradient(to right, #eff6ff, #ffffff); color: var(--text-main); padding: 15px; border-radius: 8px; font-weight: 500; border-left: 4px solid var(--primary); margin-bottom: 20px; }
    
    .tl-item { border-left: 2px solid var(--border); padding-left: 15px; margin-bottom: 20px; position: relative; }
    .tl-item::before { content: ""; position: absolute; left: -5px; top: 0; width: 8px; height: 8px; border-radius: 50%; background: var(--primary); }
    .tl-title { font-weight: 700; color: var(--text-main); font-size: 0.95rem; }
    .tl-date { font-size: 0.75rem; color: var(--text-sub); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }
    .tl-desc { font-size: 0.9rem; color: var(--text-sub); font-style: italic; margin-top: 4px; line-height: 1.4; }
    
    .skill-tag { background: white; border: 1px solid var(--border); padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; margin: 2px; display: inline-block; font-weight: 500; }
    .match { background: #f0fdf4; border-color: #86efac; color: #166534; }
    .missing { background: #fef2f2; border-color: #fecaca; color: #991b1b; text-decoration: line-through; opacity: 0.7;}
    
    .salary-box { padding: 15px; border: 1px solid #e2e8f0; border-radius: 8px; text-align: center; margin-bottom: 20px; background: white; }
    .salary-amount { font-size: 1.5rem; font-weight: 800; color: var(--text-main); }
    
    /* Tooltip */
    .tooltip { position: relative; display: inline-block; cursor: help; }
    .tooltip .tooltiptext { visibility: hidden; width: 200px; background-color: #1f2937; color: white; text-align: center; border-radius: 6px; padding: 8px; position: absolute; z-index: 1; bottom: 125%; left: 50%; margin-left: -100px; opacity: 0; transition: opacity 0.3s; font-size: 0.75rem; }
    .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }
</style>
""", unsafe_allow_html=True)

# --- 1. CLASSES & TYPES ---

DEFAULT_DATA = {
    "infos": {"nom": "Candidat", "email": "N/A", "tel": "N/A", "ville": "", "linkedin": "#", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "", "analyse": "Non estimé"},
    "analyse": {"verdict": "En attente", "points_forts": [], "points_faibles": []},
    "competences": {"match": [], "manquant": []},
    "historique": [],
    "entretien": []
}

# --- 2. FONCTIONS ROBUSTES ---

def normalize_json(raw: dict) -> dict:
    """Nettoie et valide le JSON."""
    if not isinstance(raw, dict): raw = {}
    data = DEFAULT_DATA.copy()
    
    for key in DEFAULT_DATA:
        if key in raw:
            if isinstance(DEFAULT_DATA[key], dict): 
                data[key].update(raw[key])
            else: 
                data[key] = raw[key]
    
    # Nettoyage Historique
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
    """Initialise le client API avec gestion d'erreur."""
    try: 
        if "GROQ_API_KEY" not in st.secrets:
            st.error("❌ Clé API manquante dans Secrets.")
            return None
        return openai.OpenAI(
            base_url="https://api.groq.com/openai/v1", 
            api_key=st.secrets["GROQ_API_KEY"],
            timeout=30.0  # Timeout pour éviter les blocages
        )
    except Exception as e:
        st.error(f"❌ Erreur initialisation API: {e}")
        return None

def extract_pdf_safe(file_bytes: bytes) -> Optional[str]:
    """Extraction PDF sécurisée avec gestion d'erreur."""
    try: 
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        st.error(f"❌ Erreur lecture PDF: {e}")
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_with_retry(job: str, cv: str, criteria: str = "", file_id: str = "", max_retries: int = 2) -> Optional[dict]:
    """Analyse avec retry en cas d'échec."""
    client = get_client()
    if not client: return None
    
    prompt = f"""
    ID: {file_id}
    ROLE: Expert Recrutement (Sévère et Précis).
    
    OFFRE: {job[:1500]}
    CRITERES CRITIQUES: {criteria}
    CV: {cv[:3000]}
    
    SCORING STRICT:
    - GLOBAL (0-100) : Tech (40%) + Exp (30%) + Soft (15%) + Fit (15%)
    - Sois exigeant : Si compétences clés manquantes → score < 50%
    - 80+ = Excellent match, 60-79 = Bon, 40-59 = Moyen, <40 = Inadéquat
    
    SALAIRE:
    - Estimation marché France 2025 (k€ brut annuel)
    - Ajuste selon: Séniorité + Lieu (Paris +15%) + Rareté skills
    
    JSON STRICT:
    {{
        "infos": {{ "nom": "Prénom Nom", "email": "mail@", "tel": "06...", "ville": "...", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ "min": 40, "max": 55, "confiance": "Haute", "analyse": "Justif courte" }},
        "competences": {{ "match": ["A", "B"], "manquant": ["C"] }},
        "analyse": {{ "verdict": "2 lignes max", "points_forts": ["F1", "F2"], "points_faibles": ["R1", "R2"] }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "resume_synthetique": "Impact en 2 lignes" }} ],
        "entretien": [ {{ "theme": "Technique", "question": "...", "attendu": "..." }} ]
    }}
    """
    
    for attempt in range(max_retries + 1):
        try:
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2500
            )
            return normalize_json(json.loads(res.choices[0].message.content))
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1)  # Wait avant retry
                continue
            else:
                st.warning(f"⚠️ Échec analyse après {max_retries+1} tentatives: {e}")
                return None

def save_to_sheets(data: dict, job_desc: str):
    """Sauvegarde Google Sheets avec gestion d'erreur."""
    try:
        if "gcp_service_account" not in st.secrets:
            return
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            dict(st.secrets["gcp_service_account"]), scope
        )
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        i, s = data['infos'], data['scores']
        sheet.append_row([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            i['nom'], f"{s['global']}%", i['email'], i['linkedin'], job_desc[:50]
        ])
    except Exception as e:
        st.warning(f"⚠️ Échec sauvegarde Sheets: {e}")

def export_to_excel(results: List[dict]) -> bytes:
    """Génère un fichier Excel téléchargeable."""
    flat_data = []
    for r in results:
        flat_data.append({
            'Nom': r['infos']['nom'],
            'Email': r['infos']['email'],
            'Tel': r['infos']['tel'],
            'Ville': r['infos']['ville'],
            'LinkedIn': r['infos']['linkedin'],
            'Poste Actuel': r['infos']['poste_actuel'],
            'Score Global': r['scores']['global'],
            'Score Tech': r['scores']['tech'],
            'Score Exp': r['scores']['experience'],
            'Score Soft': r['scores']['soft'],
            'Score Fit': r['scores']['fit'],
            'Salaire Min': r['salaire']['min'],
            'Salaire Max': r['salaire']['max'],
            'Verdict': r['analyse']['verdict'],
            'Compétences Match': ', '.join(r['competences']['match']),
            'Compétences Manquantes': ', '.join(r['competences']['manquant'])
        })
    
    df = pd.DataFrame(flat_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Candidats')
    return output.getvalue()

# --- 3. INTERFACE ---

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    ao_file = st.file_uploader("1️⃣ Offre d'emploi (PDF)", type='pdf', key="ao")
    ao_text = st.text_area("Ou coller le texte", height=100, placeholder="Description du poste...")
    
    job_text = ""
    if ao_file: 
        job_text = extract_pdf_safe(ao_file.getvalue())
    elif ao_text: 
        job_text = ao_text
    
    criteria = st.text_area(
        "2️⃣ Critères Non-Négociables", 
        height=80,
        placeholder="Ex: Anglais courant, Python expert, 5+ ans..."
    )
    
    cv_files = st.file_uploader("3️⃣ CVs Candidats (PDF)", type='pdf', accept_multiple_files=True)
    
    st.divider()
    
    col_btn1, col_btn2 = st.columns(2)
    launch_btn = col_btn1.button("🚀 Analyser", type="primary", use_container_width=True)
    reset_btn = col_btn2.button("🗑️ Reset", use_container_width=True)
    
    if reset_btn:
        st.session_state.results = []
        st.rerun()
    
    # Aide contextuelle
    with st.expander("ℹ️ Aide"):
        st.caption("""
        **Scoring**: 80+ = Excellent | 60-79 = Bon | 40-59 = Moyen | <40 = Inadéquat
        
        **Astuce**: Plus vos critères sont précis, plus l'IA est sévère.
        """)

# State Init
if 'results' not in st.session_state: 
    st.session_state.results = []
if 'filter_score' not in st.session_state:
    st.session_state.filter_score = 0

# --- LOGIQUE PRINCIPALE ---
if launch_btn:
    if not job_text or len(job_text) < 50:
        st.error("⚠️ L'offre doit contenir au moins 50 caractères.")
    elif not cv_files:
        st.error("⚠️ Ajoutez au moins un CV.")
    else:
        new_results = []
        
        # Progress avec détails
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        for i, file_obj in enumerate(cv_files):
            progress_text.text(f"📄 Analyse de {file_obj.name}...")
            
            file_bytes = file_obj.getvalue()
            cv_text = extract_pdf_safe(file_bytes)
            
            if cv_text and len(cv_text) > 50:
                unique_id = str(uuid.uuid4())
                data = analyze_with_retry(job_text, cv_text, criteria, file_id=unique_id)
                
                if data: 
                    save_to_sheets(data, job_text)
                    new_results.append(data)
            else:
                st.warning(f"⚠️ Fichier {file_obj.name} illisible ou vide.")
            
            progress_bar.progress((i + 1) / len(cv_files))
        
        progress_text.empty()
        progress_bar.empty()
        
        st.session_state.results = new_results
        
        if new_results:
            st.success(f"✅ {len(new_results)} candidat(s) analysé(s) avec succès !")
            st.rerun()
        else:
            st.error("❌ Aucune analyse n'a abouti. Vérifiez vos fichiers PDF.")

# --- DASHBOARD ---
if not st.session_state.results:
    st.markdown("""
    <div style="text-align: center; padding: 80px 20px;">
        <h1 style="color: var(--text-main); font-weight: 800;">AI Recruiter PRO v14</h1>
        <p style="color: var(--text-sub); font-size: 1.1rem;">Analyse intelligente de candidatures</p>
        <div style="margin-top: 50px; opacity: 0.5;">
            <p>👈 Configurez dans la barre latérale pour commencer</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    sorted_res = sorted(st.session_state.results, key=lambda x: x['scores']['global'], reverse=True)
    
    # --- KPI AMÉLIORÉS ---
    avg = int(statistics.mean([r['scores']['global'] for r in sorted_res]))
    top = sorted_res[0]['scores']['global']
    qualified = len([x for x in sorted_res if x['scores']['global'] >= 70])
    
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{len(sorted_res)}</div><div class="kpi-label">Candidats</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="kpi-card success"><div class="kpi-val">{qualified}</div><div class="kpi-label">Qualifiés (70+%)</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class="kpi-card warning"><div class="kpi-val">{avg}%</div><div class="kpi-label">Score Moyen</div></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class="kpi-card primary"><div class="kpi-val">{top}%</div><div class="kpi-label">Top Candidat</div></div>""", unsafe_allow_html=True)
    
    st.write("")
    
    # --- BARRE D'ACTIONS ---
    col_filter, col_export, col_spacer = st.columns([1, 1, 2])
    
    with col_filter:
        filter_val = st.selectbox(
            "Filtrer par score",
            options=[0, 40, 60, 70, 80],
            format_func=lambda x: f"Tous" if x == 0 else f"Score ≥ {x}%",
            key="filter_dropdown"
        )
        st.session_state.filter_score = filter_val
    
    with col_export:
        if st.button("📥 Exporter Excel", use_container_width=True):
            excel_data = export_to_excel(sorted_res)
            st.download_button(
                "💾 Télécharger",
                data=excel_data,
                file_name=f"candidats_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    st.divider()
    
    # Filtrage
    filtered_res = [r for r in sorted_res if r['scores']['global'] >= st.session_state.filter_score]
    
    if not filtered_res:
        st.warning(f"Aucun candidat avec un score ≥ {st.session_state.filter_score}%")
    
    # --- LISTE CANDIDATS ---
    for idx, d in enumerate(filtered_res):
        i = d['infos']
        s = d['scores']
        
        # Couleur sémantique du score
        if s['global'] >= 75:
            score_class = "score-high"
            score_emoji = "🌟"
        elif s['global'] >= 50:
            score_class = "score-mid"
            score_emoji = "⚡"
        else:
            score_class = "score-low"
            score_emoji = "⚠️"
        
        unique_key = f"chart_{idx}_{uuid.uuid4()}"
        
        with st.expander(f"{score_emoji} {i['nom']}  —  {s['global']}%", expanded=(idx == 0)):
            
            # Header
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
                <div class="score-badge {score_class}">{s['global']}%</div>
            </div>
            """, unsafe_allow_html=True)

            # Verdict
            st.markdown(f"""<div class="verdict">💡 <strong>Verdict:</strong> {d['analyse']['verdict']}</div>""", unsafe_allow_html=True)
            
            # Analyse Grid
            gc1, gc2 = st.columns(2)
            with gc1:
                forces_html = "".join([f"<span class='list-item txt-success'>✓ {f}</span>" for f in d['analyse']['points_forts'][:4]])
                st.markdown(f"<div class='analysis-box'><span class='analysis-title'>Points Forts</span>{forces_html}</div>", unsafe_allow_html=True)
            with gc2:
                faibles_html = "".join([f"<span class='list-item txt-danger'>✗ {f}</span>" for f in d['analyse']['points_faibles'][:4]])
                st.markdown(f"<div class='analysis-box'><span class='analysis-title'>Vigilance</span>{faibles_html}</div>", unsafe_allow_html=True)
            
            st.divider()
            
            # Détails & Viz
            col_g, col_d = st.columns([2, 1])
            
            with col_g:
                st.markdown("#### 📅 Parcours Professionnel")
                if d['historique']:
                    for h in d['historique'][:3]:
                        st.markdown(f"""
                        <div class="tl-item">
                            <div class="tl-date">{h['duree']}</div>
                            <div class="tl-title">{h['titre']} @ {h['entreprise']}</div>
                            <div class="tl-desc">{h['resume_synthetique']}</div>
                        </div>""", unsafe_allow_html=True)
                else:
                    st.caption("Historique non disponible")

            with col_d:
                # Salaire
                st.markdown(f"""
                <div class="salary-box">
                    <div style="font-size:0.7rem; color:var(--text-sub); text-transform:uppercase;">Salaire Estimé</div>
                    <div class="salary-amount">{d['salaire']['min']}-{d['salaire']['max']} k€</div>
                    <div style="font-size:0.75rem; color:var(--primary); margin-top:5px;">{d['salaire']['confiance']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Radar
                cat = ['Tech', 'Exp', 'Soft', 'Fit', 'Tech']
                val = [s['tech'], s['experience'], s['soft'], s['fit'], s['tech']]
                
                fig = go.Figure(go.Scatterpolar(
                    r=val, theta=cat, fill='toself',
                    line=dict(color='#4f46e5', width=2),
                    fillcolor='rgba(79, 70, 229, 0.15)'
                ))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, gridcolor='#e5e7eb'),
                        angularaxis=dict(tickfont=dict(size=10, color='#64748b', family='Inter'))
                    ),
                    showlegend=False,
                    margin=dict(t=20, b=20, l=30, r=30),
                    height=220,
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=unique_key)
            
            # Skills
            st.markdown("#### 🛠️ Compétences Techniques")
            skills_html = ""
            for sk in d['competences']['match']: 
                skills_html += f"<span class='skill-tag match'>✓ {sk}</span>"
            for sk in d['competences']['manquant']: 
                skills_html += f"<span class='skill-tag missing'>{sk}</span>"
            st.markdown(skills_html, unsafe_allow_html=True)
            
            # Questions
            with st.expander("🎯 Guide d'Entretien"):
                for q in d['entretien']:
                    theme_color = "#10b981" if q.get('theme') == 'Technique' else "#f59e0b"
                    st.markdown(f"<div style='border-left:3px solid {theme_color}; padding-left:10px; margin-bottom:10px;'><strong>{q.get('theme','Q')}</strong>: {q.get('question')}<br><em style='color:#64748b; font-size:0.85rem;'>Attendu: {q.get('attendu')}</em></div>", unsafe_allow_html=True)
