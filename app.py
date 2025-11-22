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

# --- 1. CONFIGURATION & STYLE CSS ---
st.set_page_config(page_title="AI Recruiter PRO - V6.0 UX", layout="wide", page_icon="💎")

# Injection CSS pour améliorer le look des badges et des cartes
st.markdown("""
<style>
    .stExpander { border-radius: 10px; border: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .metric-card { background-color: #f8f9fa; border-left: 5px solid #4CAF50; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    .skill-badge {
        display: inline-block;
        padding: 4px 12px;
        margin: 4px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        background-color: #e3f2fd;
        color: #1565c0;
        border: 1px solid #bbdefb;
    }
    .missing-badge {
        display: inline-block;
        padding: 4px 12px;
        margin: 4px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        background-color: #ffebee;
        color: #c62828;
        border: 1px solid #ffcdd2;
    }
    h3 { color: #2c3e50; font-family: 'Helvetica', sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 2. SERVICES ---
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

# --- 3. ANALYSE INTELLIGENTE ---

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    client = get_ai_client()
    if not client: return None
    
    ponderation_txt = f"PONDÉRATION: {ponderation}" if ponderation else ""
    
    prompt = f"""
    Tu es un Expert en Talent Acquisition.
    
    TACHE :
    1. Analyse le fit CV/AO.
    2. Extrais infos contact + VILLE.
    3. Estime salaire marché (Tech/France).
    
    CONTEXTE SALAIRE : Junior (35-45k), Medior (45-60k), Senior (60-90k+). Ajuste selon Paris/Province.
    
    {ponderation_txt}
    
    OFFRE (AO) : {job[:2000]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
            "tel": "Tel ou N/A",
            "ville": "Ville (ex: Lyon)",
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
            "min_k": 45,
            "max_k": 55,
            "devise": "k€",
            "justification": "Court commentaire."
        }},
        "analyse_match": {{
            "verdict_court": "Synthèse en 1 phrase.",
            "points_forts": ["Force 1", "Force 2", "Force 3"],
            "points_vigilance": ["Risque 1", "Risque 2"],
            "skills_found": ["Skill A", "Skill B", "Skill C"],
            "skills_missing": ["Skill Manquant"]
        }},
        "guide_entretien": {{
            "questions_globales": [{{"q": "Question?", "attendu": "Réponse"}}],
            "questions_techniques": [{{"q": "Question Tech?", "attendu": "Réponse Tech"}}],
            "questions_soft_skills": [{{"q": "Question Soft?", "attendu": "Réponse Soft"}}]
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
        except: time.sleep(1)
    return None

# --- 4. FRONTEND ---

if 'all_results' not in st.session_state:
    st.session_state.all_results = []

st.title("💎 AI Recruiter PRO - V6.0")

with st.sidebar:
    st.header("1. Le Besoin")
    uploaded_ao = st.file_uploader("AO (PDF)", type=['pdf'])
    ao_txt = st.text_area("Ou texte AO", height=100)
    
    job_desc = extract_text_from_pdf(uploaded_ao.getvalue()) if uploaded_ao else ao_txt
    if uploaded_ao: st.success("AO OK")

    ponderation_input = st.text_area("Critères Clés", height=70, placeholder="Ex: Anglais courant...")
    
    st.divider()
    st.header("2. Candidats")
    uploaded_files = st.file_uploader("CVs (PDF)", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🗑️ Reset"):
        st.session_state.all_results = []
        st.rerun()
    
    launch_btn = st.button("⚡ Analyser", type="primary")

if launch_btn and job_desc and uploaded_files:
    st.write(f"Analyse de {len(uploaded_files)} profil(s)...")
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

# --- 5. AFFICHAGE UI/UX AMÉLIORÉ ---
if st.session_state.all_results:
    df = pd.DataFrame(st.session_state.all_results)
    df = df.sort_values('Score', ascending=False)
    
    st.subheader("📊 Tableau de Bord")
    st.dataframe(
        df.drop(columns=['full']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "LinkedIn": st.column_config.LinkColumn("Profil", display_text="Voir"),
            "Score": st.column_config.ProgressColumn("Match", format="%d%%", min_value=0, max_value=100)
        }
    )
    
    st.markdown("---")
    st.subheader("👤 Détail des Profils")

    for idx, row in df.iterrows():
        d = row['full']
        score = row['Score']
        
        # Badge couleur score
        score_color = "#4CAF50" if score >= 75 else "#ff9800" if score >= 50 else "#f44336"
        score_emoji = "🌟 Excellent" if score >= 75 else "👍 Bon" if score >= 50 else "⚠️ Risqué"
        
        # --- HEADER CARTE ---
        with st.expander(f"{d['infos']['nom']}  |  {score_emoji} ({score}%)", expanded=False):
            
            # 1. BARRE DE CONTACT (Compacte et Propre)
            st.markdown(
                f"""
                <div style="background-color:#f9f9f9; padding:10px; border-radius:8px; display:flex; justify-content:space-around; align-items:center; font-size:0.9em; border:1px solid #eee;">
                    <span>📧 {d['infos'].get('email', 'N/A')}</span>
                    <span>📱 {d['infos'].get('tel', 'N/A')}</span>
                    <span>📍 {d['infos'].get('ville', 'N/A')}</span>
                    <span>🔗 <a href="{d['infos'].get('linkedin', '#')}" target="_blank" style="text-decoration:none; color:#0077b5; font-weight:bold;">LinkedIn</a></span>
                </div>
                <br>
                """, unsafe_allow_html=True
            )

            # 2. TABS POUR UX FLUIDE
            tab_synthese, tab_skills, tab_interview = st.tabs(["🏠 Synthèse 360°", "🛠️ Compétences & Marché", "🎤 Guide Entretien"])
            
            # --- TAB 1: SYNTHÈSE ---
            with tab_synthese:
                c_verdict, c_radar = st.columns([2, 1])
                
                with c_verdict:
                    st.markdown("#### 💡 Verdict de l'IA")
                    st.info(d['analyse_match']['verdict_court'])
                    
                    c_plus, c_moins = st.columns(2)
                    with c_plus:
                        st.markdown("**✅ Les Plus :**")
                        for p in d['analyse_match']['points_forts']:
                            st.markdown(f"<div style='margin-bottom:4px;'>• {p}</div>", unsafe_allow_html=True)
                    with c_moins:
                        st.markdown("**🚨 Points d'attention :**")
                        for v in d['analyse_match']['points_vigilance']:
                            st.markdown(f"<div style='color:#d32f2f; margin-bottom:4px;'>• {v}</div>", unsafe_allow_html=True)
                
                with c_radar:
                    vals = [d['scores']['tech'], d['scores']['exp'], d['scores']['soft'], d['scores']['culture']]
                    fig = go.Figure(data=go.Scatterpolar(r=vals, theta=['Tech', 'Exp', 'Soft', 'Culture'], fill='toself'))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=200, margin=dict(t=20, b=20, l=30, r=30))
                    st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

            # --- TAB 2: COMPÉTENCES & MARCHÉ ---
            with tab_skills:
                col_skill_list, col_market = st.columns([2, 1])
                
                with col_skill_list:
                    st.markdown("#### 🧩 Stack Technique détectée")
                    skills_html = ""
                    for s in d['analyse_match'].get('skills_found', []):
                        skills_html += f"<span class='skill-badge'>{s}</span>"
                    st.markdown(skills_html if skills_html else "Pas de skills spécifiques détectés.", unsafe_allow_html=True)
                    
                    st.markdown("#### ❌ Compétences Manquantes")
                    miss_html = ""
                    for m in d['analyse_match'].get('skills_missing', []):
                        miss_html += f"<span class='missing-badge'>{m}</span>"
                    st.markdown(miss_html if miss_html else "Rien de critique manquant.", unsafe_allow_html=True)

                with col_market:
                    st.markdown("#### 💰 Estimation Marché")
                    sal = d.get('market_value', {})
                    min_k = sal.get('min_k', 0)
                    max_k = sal.get('max_k', 0)
                    
                    st.metric(
                        label="Salaire Brut Annuel Estimé",
                        value=f"{min_k} - {max_k} k€",
                        delta=f"Moyenne: {(min_k+max_k)/2} k€",
                        delta_color="off"
                    )
                    st.caption(f"ℹ️ {sal.get('justification', '')}")

            # --- TAB 3: GUIDE ENTRETIEN ---
            with tab_interview:
                st.markdown("#### 🎯 Cheat Sheet pour l'interviewer")
                guide = d.get('guide_entretien', {})
                
                # Utilisation de colonnes pour aérer
                cg1, cg2 = st.columns(2)
                
                with cg1:
                    st.markdown("##### 🌍 Questions Parcours")
                    for q in guide.get('questions_globales', []):
                        with st.expander(f"❓ {q['q']}"):
                            st.markdown(f"**Attendu :** {q['attendu']}")
                            
                    st.markdown("##### 🤝 Soft Skills")
                    for q in guide.get('questions_soft_skills', []):
                        with st.expander(f"❓ {q['q']}"):
                            st.markdown(f"**Attendu :** {q['attendu']}")

                with cg2:
                    st.markdown("##### 💻 Questions Techniques")
                    for q in guide.get('questions_techniques', []):
                        with st.expander(f"❓ {q['q']}"):
                            st.markdown(f"**Attendu :** {q['attendu']}")

elif not launch_btn:
    st.info("👈 Commencez par charger l'AO et les CVs dans le menu latéral.")
