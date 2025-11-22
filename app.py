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
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="AI Recruiter PRO - V4.5 Interview Edition", layout="wide", page_icon="🎯")

# --- 2. SERVICES & UTILS ---
def get_ai_client():
    try:
        if "GROQ_API_KEY" in st.secrets:
            return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None
    return None

def save_to_google_sheet(data, job_desc):
    """Sauvegarde avec gestion d'erreurs silencieuse"""
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d"), 
                data['infos']['nom'], 
                f"{data['scores']['global']}%",
                data['infos']['email'],
                data['infos'].get('linkedin', 'N/A'),
                job_desc.split('\n')[0][:50]
            ])
    except: pass

@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes):
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        return "".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except: return ""

# --- 3. CŒUR DU SYSTÈME : ANALYSE PROFONDE ---

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    client = get_ai_client()
    if not client: return None
    
    ponderation_txt = f"PONDÉRATION CLIENT: {ponderation}" if ponderation else "Pas de pondération spécifique."
    
    prompt = f"""
    Tu es un Expert en Recrutement Technique & Psychologie du travail.
    
    TACHE :
    1. Analyse le fit entre le CV et l'AO.
    2. Construit un GUIDE D'ENTRETIEN complet avec les réponses attendues ("Cheat Sheet").
    
    {ponderation_txt}
    
    OFFRE (AO) : {job[:2000]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
            "linkedin": "URL LinkedIn ou N/A",
            "tel": "Tel ou N/A",
            "annees_exp": "X ans (Requis: Y ans)",
            "poste_actuel": "Titre actuel"
        }},
        "scores": {{
            "global": 0-100,
            "tech": 0-10,
            "exp": 0-10,
            "soft": 0-10,
            "culture": 0-10
        }},
        "analyse_match": {{
            "verdict_court": "Une phrase percutante de synthèse.",
            "points_forts": ["Force 1 (contexte)", "Force 2"],
            "points_vigilance": ["Risque 1 (ex: job hopping)", "Manque Skill X"],
            "skills_missing": ["Skill A", "Skill B"]
        }},
        "guide_entretien": {{
            "questions_globales": [
                {{"q": "Question brise-glace ou parcours", "attendu": "Ce qu'on veut entendre"}}
            ],
            "questions_techniques": [
                {{"q": "Question technique précise sur une compétence de l'AO", "attendu": "La réponse technique correcte ou mots-clés attendus"}}
            ],
            "questions_soft_skills": [
                {{"q": "Question situationnelle (STAR method)", "attendu": "Comportement recherché"}}
            ]
        }}
    }}
    """
    
    for _ in range(3): # Retry simple
        try:
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            return json.loads(res.choices[0].message.content)
        except Exception: time.sleep(1)
    return None

# --- 4. FRONTEND ---

if 'all_results' not in st.session_state:
    st.session_state.all_results = []

st.title("🎯 AI Recruiter PRO - Interview Edition")

with st.sidebar:
    st.header("1. Le Besoin (AO)")
    uploaded_ao = st.file_uploader("📄 AO (PDF)", type=['pdf'])
    ao_txt = st.text_area("Ou texte AO", height=100)
    
    job_desc = extract_text_from_pdf(uploaded_ao.getvalue()) if uploaded_ao else ao_txt
    if uploaded_ao: st.success("AO PDF chargée !")

    st.subheader("Critères")
    ponderation_input = st.text_area("Pondération", placeholder="Ex: Anglais obligatoire, Python expert...", height=70)
    
    st.divider()
    st.header("2. Les Candidats")
    uploaded_files = st.file_uploader("CVs (PDF)", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🗑️ Reset"):
        st.session_state.all_results = []
        st.rerun()

    launch_btn = st.button("⚡ Analyser", type="primary")

if launch_btn and job_desc and uploaded_files:
    st.write(f"🔍 Analyse approfondie de {len(uploaded_files)} profil(s)...")
    bar = st.progress(0)
    batch_res = []
    
    for i, file in enumerate(uploaded_files):
        txt = extract_text_from_pdf(file.getvalue())
        if txt:
            d = analyze_candidate_deep(job_desc, txt, ponderation_input)
            if d:
                save_to_google_sheet(d, job_desc)
                # Nettoyage Lien
                lnk = d['infos'].get('linkedin', 'N/A')
                final_lnk = lnk if lnk and 'http' in lnk else None
                
                batch_res.append({
                    'Nom': d['infos']['nom'],
                    'Score': d['scores']['global'],
                    'Exp': d['infos']['annees_exp'],
                    'LinkedIn': final_lnk,
                    'full': d
                })
        bar.progress((i+1)/len(uploaded_files))
    
    st.session_state.all_results = batch_res
    bar.empty()
    st.rerun()

# --- 5. AFFICHAGE ---
if st.session_state.all_results:
    df = pd.DataFrame(st.session_state.all_results)
    df = df.sort_values('Score', ascending=False)
    
    # Tableau
    st.subheader("📊 Vue d'ensemble")
    st.dataframe(
        df.drop(columns=['full']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "LinkedIn": st.column_config.LinkColumn("Profil", display_text="Voir"),
            "Score": st.column_config.ProgressColumn("Match", format="%d%%", min_value=0, max_value=100)
        }
    )
    
    st.divider()
    st.header("📝 Dossiers Candidats & Guide d'Entretien")

    for idx, row in df.iterrows():
        d = row['full']
        score = row['Score']
        color = "green" if score >= 75 else "orange" if score >= 50 else "red"
        
        with st.expander(f"**{d['infos']['nom']}** - :{color}[{score}%] - {d['infos'].get('poste_actuel', '')}", expanded=False):
            
            # --- BLOC 1 : SYNTHÈSE VISUELLE ---
            c1, c2, c3 = st.columns([1, 1, 1])
            
            with c1:
                st.markdown("#### 🧠 Verdict")
                st.info(d['analyse_match']['verdict_court'])
                if row['LinkedIn']:
                    st.markdown(f"🔗 [**Profil LinkedIn**]({row['LinkedIn']})")
            
            with c2:
                st.markdown("#### 📊 Radar")
                vals = [d['scores']['tech'], d['scores']['exp'], d['scores']['soft'], d['scores']['culture']]
                fig = go.Figure(data=go.Scatterpolar(r=vals, theta=['Tech', 'Exp', 'Soft', 'Culture'], fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=150, margin=dict(t=0, b=0, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

            with c3:
                st.markdown("#### ⚠️ Manquants")
                if d['analyse_match']['skills_missing']:
                    for s in d['analyse_match']['skills_missing']:
                        st.markdown(f"❌ {s}")
                else:
                    st.success("Aucun manque critique détecté.")

            # --- BLOC 2 : FORCES vs FAIBLESSES ---
            st.markdown("---")
            c_force, c_faible = st.columns(2)
            with c_force:
                st.success("✅ **Points Forts**")
                for f in d['analyse_match']['points_forts']: st.write(f"- {f}")
            with c_faible:
                st.warning("🚨 **Points de Vigilance**")
                for v in d['analyse_match']['points_vigilance']: st.write(f"- {v}")

            # --- BLOC 3 : LE GUIDE D'ENTRETIEN (AMÉLIORÉ) ---
            st.markdown("---")
            st.subheader("🎤 Guide d'Entretien & Attentes")
            
            guide = d.get('guide_entretien', {})
            
            t1, t2, t3 = st.tabs(["🌍 Général & Parcours", "💻 Technique & Hard Skills", "🤝 Soft Skills & Culture"])
            
            def display_questions(q_list):
                if not q_list: st.write("Pas de questions générées."); return
                for q_item in q_list:
                    # Utilisation d'un expander interne pour cacher la réponse
                    with st.container():
                        st.markdown(f"**❓ {q_item['q']}**")
                        with st.expander("👁️ Voir la réponse attendue (Indice)"):
                            st.markdown(f"💡 *{q_item['attendu']}*")
                        st.write("") # Spacer

            with t1:
                display_questions(guide.get('questions_globales', []))
            with t2:
                display_questions(guide.get('questions_techniques', []))
            with t3:
                display_questions(guide.get('questions_soft_skills', []))

elif not launch_btn:
    st.info("👈 Commencez par charger l'AO et les CVs.")
