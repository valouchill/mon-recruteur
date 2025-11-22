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
st.set_page_config(page_title="AI Recruiter PRO - V5.0 Full Profile", layout="wide", page_icon="💎")

# --- 2. SERVICES & UTILS ---
def get_ai_client():
    try:
        if "GROQ_API_KEY" in st.secrets:
            return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None
    return None

def save_to_google_sheet(data, job_desc):
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

# --- 3. CŒUR DU SYSTÈME : ANALYSE ENRICHIE ---

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    client = get_ai_client()
    if not client: return None
    
    ponderation_txt = f"PONDÉRATION: {ponderation}" if ponderation else ""
    
    prompt = f"""
    Tu es un Expert en Recrutement et Rémunération.
    
    TACHE :
    1. Analyse le fit CV/AO.
    2. Extrais précisément les contacts (Email, Tel, VILLE DE RÉSIDENCE).
    3. Estime la VALEUR MARCHÉ (Salaire) du candidat.
    
    CONTEXTE SALAIRE : 
    Base ton estimation sur le marché actuel (Tech/Digital) en prenant en compte :
    - L'expérience (Junior/Medior/Senior)
    - La localisation (Paris vs Province, à déduire du CV ou de l'AO)
    - La rareté des compétences.
    
    {ponderation_txt}
    
    OFFRE (AO) : {job[:2000]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
            "tel": "Tel format standard ou N/A",
            "ville": "Ville/Région (ex: Lyon, IDF...)",
            "linkedin": "URL ou N/A",
            "annees_exp": "X ans",
            "poste_actuel": "Titre"
        }},
        "scores": {{
            "global": 0-100,
            "tech": 0-10,
            "exp": 0-10,
            "soft": 0-10,
            "culture": 0-10
        }},
        "market_value": {{
            "fourchette_k": "XXk - YYk",
            "devise": "€",
            "justification": "Ex: Profil Senior sur stack rare (Rust), marché parisien tendu."
        }},
        "analyse_match": {{
            "verdict_court": "Synthèse percutante.",
            "points_forts": ["Force 1", "Force 2"],
            "points_vigilance": ["Risque 1", "Risque 2"],
            "skills_missing": ["Skill A"]
        }},
        "guide_entretien": {{
            "questions_globales": [
                {{"q": "Question parcours", "attendu": "Réponse cible"}}
            ],
            "questions_techniques": [
                {{"q": "Question technique", "attendu": "Mots-clés techniques"}}
            ],
            "questions_soft_skills": [
                {{"q": "Question soft skill", "attendu": "Comportement"}}
            ]
        }}
    }}
    """
    
    for _ in range(3):
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

st.title("💎 AI Recruiter PRO - V5.0")

with st.sidebar:
    st.header("1. Le Besoin (AO)")
    uploaded_ao = st.file_uploader("📄 AO (PDF)", type=['pdf'])
    ao_txt = st.text_area("Ou texte AO", height=100)
    
    job_desc = extract_text_from_pdf(uploaded_ao.getvalue()) if uploaded_ao else ao_txt
    if uploaded_ao: st.success("AO chargée !")

    st.subheader("Critères")
    ponderation_input = st.text_area("Pondération", height=70)
    
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
    st.header("📝 Dossiers Complets")

    for idx, row in df.iterrows():
        d = row['full']
        score = row['Score']
        color = "green" if score >= 75 else "orange" if score >= 50 else "red"
        
        with st.expander(f"**{d['infos']['nom']}** - :{color}[{score}%] - {d['infos'].get('poste_actuel', '')}", expanded=False):
            
            # --- NOUVEAU BLOC 1 : INFORMATIONS DE CONTACT ---
            st.markdown("### 📇 Coordonnées")
            c_cont1, c_cont2, c_cont3, c_cont4 = st.columns(4)
            
            with c_cont1:
                st.markdown(f"📧 **Email**\n\n`{d['infos'].get('email', 'N/A')}`")
            with c_cont2:
                st.markdown(f"📞 **Téléphone**\n\n`{d['infos'].get('tel', 'N/A')}`")
            with c_cont3:
                st.markdown(f"📍 **Localisation**\n\n`{d['infos'].get('ville', 'Non précisée')}`")
            with c_cont4:
                lnk_display = d['infos'].get('linkedin', 'N/A')
                if 'http' in lnk_display:
                    st.markdown(f"🔗 **LinkedIn**\n\n[Voir le profil]({lnk_display})")
                else:
                    st.markdown("🔗 **LinkedIn**\n\nN/A")
            
            st.divider()

            # --- BLOC 2 : ANALYSE & SALAIRE ---
            c_main, c_salary = st.columns([2, 1])
            
            with c_main:
                st.info(f"🧠 **Verdict:** {d['analyse_match']['verdict_court']}")
                
                # Radar
                vals = [d['scores']['tech'], d['scores']['exp'], d['scores']['soft'], d['scores']['culture']]
                fig = go.Figure(data=go.Scatterpolar(r=vals, theta=['Tech', 'Exp', 'Soft', 'Culture'], fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=180, margin=dict(t=10, b=10, l=30, r=30))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

            # --- NOUVEAU BLOC : INTELLIGENCE MARCHÉ (SALAIRE) ---
            with c_salary:
                st.markdown("### 💰 Valeur Marché Estimée")
                salary_data = d.get('market_value', {})
                
                # Container stylé pour le salaire
                st.markdown(
                    f"""
                    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #d1d5db;">
                        <h2 style="color: #0068c9; margin:0;">{salary_data.get('fourchette_k', 'N/A')} {salary_data.get('devise', '€')}</h2>
                        <p style="font-size: 0.9em; color: #555; margin-top:5px;">Brut Annuel Estimé</p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                st.markdown("**Justification IA :**")
                st.caption(salary_data.get('justification', "Pas assez de données pour estimer."))

            # --- BLOC 3 : FORCES / FAIBLESSES ---
            c_f, c_w = st.columns(2)
            with c_f:
                st.success("✅ **Points Forts**")
                for x in d['analyse_match']['points_forts']: st.write(f"- {x}")
            with c_w:
                st.error("🚨 **Points de Vigilance**")
                for x in d['analyse_match']['points_vigilance']: st.write(f"- {x}")

            # --- BLOC 4 : GUIDE D'ENTRETIEN ---
            st.divider()
            st.subheader("🎤 Guide d'Entretien")
            
            guide = d.get('guide_entretien', {})
            t1, t2, t3 = st.tabs(["Général", "Technique", "Soft Skills"])
            
            def show_q(lst):
                if not lst: st.write("N/A"); return
                for item in lst:
                    with st.container():
                        st.write(f"❓ **{item['q']}**")
                        with st.expander("💡 Réponse attendue"):
                            st.caption(item['attendu'])
            
            with t1: show_q(guide.get('questions_globales', []))
            with t2: show_q(guide.get('questions_techniques', []))
            with t3: show_q(guide.get('questions_soft_skills', []))

elif not launch_btn:
    st.info("👈 Chargez l'AO et les CVs pour démarrer.")
