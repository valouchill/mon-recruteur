import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import plotly.express as px
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import io
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="AI Recruiter PRO - V8.0", layout="wide", page_icon="👔")

# CSS optimisé
st.markdown("""
<style>
.metric-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; text-align: center; }
.st-expanderHeader { font-weight: 600 !important; }
.status-green { background: #d4edda; color: #155724; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
.status-orange { background: #fff3cd; color: #856404; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
.status-red { background: #f8d7da; color: #721c24; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --- UTILITAIRES ROBUSTES ---
@st.cache_data(ttl=3600)
def get_ai_client():
    try:
        return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None

def safe_json_parse(response_text):
    """Parse JSON avec fallback sécurisé"""
    try:
        return json.loads(response_text)
    except:
        return {
            "infos": {"nom": "Erreur parsing", "email": "N/A"},
            "scores": {"global": 0}, "analyse": {"verdict": "Erreur JSON"}
        }

def save_to_sheets(data, job_desc):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        infos, scores = data.get('infos', {}), data.get('scores', {})
        sheet.append_row([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
            infos.get('nom'), f"{scores.get('global')}%",
            infos.get('email'), infos.get('linkedin', ''), 
            job_desc[:50]
        ])
    except: pass

@st.cache_data
def extract_pdf_text(file_bytes):
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        return "".join(page.extract_text() for page in reader.pages if page.extract_text())
    except: return ""

# --- PROMPT IA OPTIMISÉ ---
@st.cache_data(ttl=1800)
def analyze_cv(job_desc, cv_text, criteria=""):
    client = get_ai_client()
    if not client: return None
    
    prompt = f"""ANALYSE RECRUTEMENT TECHNIQUE

OFFRE: {job_desc[:2000]}
CRITÈRES: {criteria}
CV: {cv_text[:4000]}

EXTRAIS et ANALYSE en JSON STRICT:
{{
  "infos": {{"nom": "NOM", "email": "email@ex.com", "tel": "01.xx.xx.xx.xx", "ville": "Paris", "linkedin": "https://linkedin.com/in/...", "experience": "5 ans"}},
  "scores": {{"global": 85, "tech": 9, "experience": 8, "soft": 7, "culture": 8}},
  "salaire": {{"min": 45, "max": 55, "justif": "Senior Python Paris"}},
  "historique": [{{"titre": "Dev Senior", "entreprise": "Société", "duree": "2022-Aujourd'hui", "mission": "Description"}}],
  "competences": {{"expert": ["Python", "AWS"], "intermediaire": ["Docker"], "manquant": ["Kubernetes"]}},
  "forces": ["5 ans exp Python", "Projets AWS"],
  "risques": ["Pas de K8s"],
  "questions": [{{"type": "tech", "question": "Explique un déploiement AWS", "attendu": "Détails ELB/EC2"}}]
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000
        )
        return safe_json_parse(response.choices[0].message.content)
    except: return None

# --- INTERFACE PRINCIPALE ---
if 'results' not in st.session_state:
    st.session_state.results = []

st.title("👔 AI Recruiter PRO - V8.0")

# SIDEBAR ENRICHIE
with st.sidebar:
    st.header("📋 Configuration")
    
    # AO
    ao_pdf = st.file_uploader("📄 Offre d'emploi (PDF)", type='pdf')
    ao_text = st.text_area("Ou texte AO", height=120, placeholder="Collez l'offre...")
    job_offer = extract_pdf_text(ao_pdf.getvalue()) if ao_pdf else ao_text
    
    st.divider()
    
    # Critères
    criteria = st.text_area("⚖️ Critères prioritaires", height=80, 
                          placeholder="Ex: Python obligatoire, 3+ ans exp, IDF...")
    
    # Upload CVs
    cvs = st.file_uploader("📋 CVs (PDFs)", type='pdf', accept_multiple_files=True)
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1: if st.button("🔄 Analyser", type="primary"): st.session_state.analyze = True
    with col2: if st.button("🗑️ Reset"): st.session_state.results = []; st.rerun()
    
    # Stats sidebar
    if st.session_state.results:
        df_stats = pd.DataFrame(st.session_state.results)
        st.metric("Candidats", len(df_stats))
        st.metric("Meilleur score", f"{df_stats['score'].max()}%")

# LOGIQUE ANALYSE
if st.session_state.get('analyze', False) and job_offer and cvs:
    st.session_state.analyze = False
    with st.spinner(f'Analyse de {len(cvs)} CVs...'):
        results = []
        progress = st.progress(0)
        
        for i, cv_file in enumerate(cvs):
            cv_text = extract_pdf_text(cv_file.getvalue())
            if cv_text:
                analysis = analyze_cv(job_offer, cv_text, criteria)
                if analysis:
                    save_to_sheets(analysis, job_offer)
                    
                    # Formatage sécurisé
                    info = analysis.get('infos', {})
                    score_data = analysis.get('scores', {'global': 0})
                    
                    results.append({
                        'nom': info.get('nom', 'N/A'),
                        'score': int(score_data.get('global', 0)),
                        'email': info.get('email', 'N/A'),
                        'linkedin': info.get('linkedin', None),
                        'salaire': f"{analysis.get('salaire', {}).get('min', 0)}-{analysis.get('salaire', {}).get('max', 0)}k€",
                        'data': analysis
                    })
            progress.progress((i+1)/len(cvs))
        
        st.session_state.results = results
        st.rerun()

# AFFICHAGE RÉSULTATS
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    df = df.sort_values('score', ascending=False)
    
    # FILTRES
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_score = st.slider("Score min", 0, 100, 50)
    with col_f2:
        status_filter = st.selectbox("Statut", ["Tous", "Top 3", "≥75%", "50-74%", "<50%"])
    
    df_filtered = df[df['score'] >= min_score].copy()
    
    # EXPORT
    csv_data = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Excel", csv_data, "recrutement.csv", "text/csv")
    
    st.subheader("📊 Tableau de Bord")
    st.dataframe(
        df_filtered.drop('data', axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "linkedin": st.column_config.LinkColumn("LinkedIn"),
            "score": st.column_config.ProgressColumn("Score", "%d%%"),
        }
    )
    
    # FICHES CANDIDATS
    st.subheader("👥 Dossiers Détaillés")
    for idx, candidate in df_filtered.iterrows():
        data = candidate['data']
        score = candidate['score']
        
        status_class = "status-green" if score >= 75 else "status-orange" if score >= 50 else "status-red"
        
        with st.expander(f"👤 **{candidate['nom']}** • {score}% • {candidate['salaire']}", expanded=False):
            
            # HEADER
            info = data.get('infos', {})
            col1, col2, col3 = st.columns([1,1,1])
            with col1: st.markdown(f"**📧** {info.get('email', 'N/A')}")
            with col2: st.markdown(f"**📍** {info.get('ville', 'N/A')}")
            with col3: st.markdown(f"**🔗** {info.get('linkedin', 'N/A')}")
            
            # Layout 60/40
            main_col, side_col = st.columns([3, 2])
            
            with main_col:
                st.markdown("### 🎯 Analyse")
                st.success(data.get('analyse', {}).get('verdict', 'N/A'))
                
                # Forces / Risques
                forces = data.get('forces', [])
                risques = data.get('risques', [])
                
                c_f, c_r = st.columns(2)
                with c_f:
                    st.markdown("**✅ Forces**")
                    for force in forces[:3]:
                        st.markdown(f"• {force}")
                with c_r:
                    st.markdown("**⚠️ Risques**")
                    for risque in risques:
                        st.error(f"• {risque}")
                
                # Historique
                hist = data.get('historique', [])
                if hist:
                    st.markdown("### 📈 Parcours Pro")
                    for poste in hist[:3]:
                        st.markdown(f"**{poste.get('titre')}** chez _{poste.get('entreprise')}_")
                        st.caption(poste.get('mission', ''))
            
            with side_col:
                # Radar
                scores = data.get('scores', {})
                fig = go.Figure(data=go.Scatterpolar(
                    r=[scores.get('tech',0), scores.get('experience',0), 
                       scores.get('soft',0), scores.get('culture',0)],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself'
                ))
                fig.update_layout(height=250, margin=20)
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")
                
                # Compétences
                skills = data.get('competences', {})
                st.markdown("### 🛠️ Skills")
                
                expert = skills.get('expert', [])
                if expert:
                    st.markdown("**🏆 Expert**")
                    for skill in expert:
                        st.markdown(f"✅ {skill}")
                
                missing = skills.get('manquant', [])
                if missing:
                    st.markdown("**❌ Manque**")
                    for skill in missing:
                        st.markdown(f"❌ {skill}")
    
    # Questions (top candidats)
    top_candidates = df_filtered.head(3)
    if not top_candidates.empty:
        st.markdown("---")
        st.subheader("🎤 Questions pour Top Candidats")
        for _, cand in top_candidates.iterrows():
            questions = cand['data'].get('questions', [])
            if questions:
                st.markdown(f"**{cand['nom']}** ({cand['score']}%)")
                for q in questions[:2]:
                    with st.expander(q.get('question', 'N/A')):
                        st.caption(f"💡 Attendu: {q.get('attendu', 'N/A')}")

else:
    st.info("👈 **Chargez l'offre + CVs** pour lancer l'analyse")
    st.balloons()
