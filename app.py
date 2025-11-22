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
st.set_page_config(page_title="AI Recruiter PRO - V6.1 Single View", layout="wide", page_icon="💎")

st.markdown("""
<style>
    .stExpander { border-radius: 8px; border: 1px solid #ddd; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 10px; }
    .contact-bar { background-color: #f0f2f6; padding: 12px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 15px; font-size: 0.95em; display: flex; justify-content: space-around; align-items: center; }
    .verdict-box { background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 15px; border-radius: 4px; margin-bottom: 15px; color: #0d47a1; }
    .skill-badge { display: inline-block; padding: 5px 10px; margin: 3px; border-radius: 12px; font-size: 0.85em; font-weight: 600; background-color: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
    .missing-badge { display: inline-block; padding: 5px 10px; margin: 3px; border-radius: 12px; font-size: 0.85em; font-weight: 600; background-color: #ffebee; color: #c62828; border: 1px solid #ffcdd2; }
    h4 { color: #333; border-bottom: 2px solid #f0f2f6; padding-bottom: 5px; margin-top: 20px; margin-bottom: 15px; }
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
    2. Extrais infos contact + VILLE + Estime SALAIRE (Tech France).
    3. Construit un GUIDE D'ENTRETIEN structuré.
    
    CONTEXTE SALAIRE : Estime une fourchette réaliste (ex: 45-55k) selon expérience et lieu.
    
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
            "poste_actuel": "Titre actuel"
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
            "justification": "Commentaire court salaire."
        }},
        "analyse_match": {{
            "verdict_court": "Synthèse percutante.",
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

st.title("💎 AI Recruiter PRO - Single View")

with st.sidebar:
    st.header("1. Le Besoin")
    uploaded_ao = st.file_uploader("AO (PDF)", type=['pdf'])
    ao_txt = st.text_area("Ou texte AO", height=100)
    job_desc = extract_text_from_pdf(uploaded_ao.getvalue()) if uploaded_ao else ao_txt
    
    ponderation_input = st.text_area("Critères Clés", height=70)
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

# --- 5. AFFICHAGE SANS ONGLETS ---
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
    
    st.divider()
    st.header("👤 Dossiers Candidats")

    for idx, row in df.iterrows():
        d = row['full']
        score = row['Score']
        score_emoji = "🌟 Excellent" if score >= 75 else "👍 Bon" if score >= 50 else "⚠️ Moyen"
        
        with st.expander(f"{d['infos']['nom']}  |  {score_emoji} ({score}%)  |  {d['infos'].get('poste_actuel','Candidat')}", expanded=False):
            
            # 1. BARRE CONTACT
            st.markdown(
                f"""
                <div class="contact-bar">
                    <span>📧 {d['infos'].get('email', 'N/A')}</span>
                    <span>📱 {d['infos'].get('tel', 'N/A')}</span>
                    <span>📍 {d['infos'].get('ville', 'N/A')}</span>
                    <span>🔗 <a href="{d['infos'].get('linkedin', '#')}" target="_blank">LinkedIn</a></span>
                </div>
                """, unsafe_allow_html=True
            )

            # 2. BLOC STRATÉGIQUE (Verdict + Radar + Salaire)
            c_verdict, c_radar = st.columns([2, 1])
            
            with c_verdict:
                st.markdown(f"<div class='verdict-box'><b>🧠 Verdict IA :</b> {d['analyse_match']['verdict_court']}</div>", unsafe_allow_html=True)
                
                # Sous-colonnes pour Forces / Salaire
                c_pros, c_market = st.columns(2)
                with c_pros:
                    st.markdown("**✅ Points Forts :**")
                    for p in d['analyse_match']['points_forts']: st.markdown(f"- {p}")
                    st.markdown("**🚨 Vigilance :**")
                    for v in d['analyse_match']['points_vigilance']: st.markdown(f"- {v}")
                
                with c_market:
                    st.markdown("**💰 Valeur Marché Estimée**")
                    sal = d.get('market_value', {})
                    st.metric("Salaire Brut", f"{sal.get('min_k',0)}-{sal.get('max_k',0)} k€")
                    st.caption(sal.get('justification', ''))

            with c_radar:
                # Graphique
                vals = [d['scores']['tech'], d['scores']['exp'], d['scores']['soft'], d['scores']['culture']]
                fig = go.Figure(data=go.Scatterpolar(r=vals, theta=['Tech', 'Exp', 'Soft', 'Culture'], fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=220, margin=dict(t=20, b=20, l=30, r=30))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

            # 3. BLOC TECHNIQUE (Badges)
            st.markdown("---")
            st.markdown("#### 🧩 Compétences Détectées")
            
            skills_html = ""
            for s in d['analyse_match'].get('skills_found', []): skills_html += f"<span class='skill-badge'>{s}</span>"
            st.markdown(skills_html if skills_html else "N/A", unsafe_allow_html=True)
            
            if d['analyse_match'].get('skills_missing'):
                miss_html = "<br><b>Manquants : </b>"
                for m in d['analyse_match'].get('skills_missing', []): miss_html += f"<span class='missing-badge'>{m}</span>"
                st.markdown(miss_html, unsafe_allow_html=True)

            # 4. BLOC ENTRETIEN (3 Colonnes)
            st.markdown("#### 🎤 Guide d'Entretien")
            guide = d.get('guide_entretien', {})
            
            gc1, gc2, gc3 = st.columns(3)
            
            def show_q_col(col, title, questions):
                with col:
                    st.markdown(f"**{title}**")
                    if not questions: st.caption("Aucune suggestion.")
                    for i, q in enumerate(questions):
                        # Clé unique pour chaque question
                        with st.expander(f"❓ {q['q'][:40]}...", expanded=False):
                            st.write(f"**Q:** {q['q']}")
                            st.caption(f"💡 **Attendu:** {q['attendu']}")

            show_q_col(gc1, "🌍 Parcours", guide.get('questions_globales', []))
            show_q_col(gc2, "💻 Technique", guide.get('questions_techniques', []))
            show_q_col(gc3, "🤝 Soft Skills", guide.get('questions_soft_skills', []))

elif not launch_btn:
    st.info("👈 Importez vos fichiers dans la barre latérale pour commencer.")
