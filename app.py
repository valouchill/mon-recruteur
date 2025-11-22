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

# --- 1. CONFIGURATION & CSS PRO ---
st.set_page_config(page_title="AI Recruiter PRO - V7 Dashboard", layout="wide", page_icon="👔")

st.markdown("""
<style>
    /* Style des Headers */
    h3 { color: #1f2937; font-weight: 700; font-size: 1.2rem; margin-top: 0px; border-bottom: 2px solid #f3f4f6; padding-bottom: 10px; }
    h4 { color: #4b5563; font-size: 1rem; font-weight: 600; margin-top: 15px; }
    
    /* Badges Compétences */
    .badge-expert { background-color: #d1fae5; color: #065f46; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; border: 1px solid #a7f3d0; display: inline-block; margin: 2px;}
    .badge-inter { background-color: #dbeafe; color: #1e40af; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; border: 1px solid #bfdbfe; display: inline-block; margin: 2px;}
    .badge-junior { background-color: #f3f4f6; color: #374151; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; border: 1px solid #e5e7eb; display: inline-block; margin: 2px;}
    
    /* Boites d'alertes personnalisées */
    .box-pro { background-color: #f0fdf4; border-left: 4px solid #22c55e; padding: 10px; border-radius: 4px; margin-bottom: 5px; color: #166534; font-size: 0.9rem; }
    .box-con { background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 10px; border-radius: 4px; margin-bottom: 5px; color: #991b1b; font-size: 0.9rem; }
    
    /* Contact Info */
    .contact-row { background: #fff; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .contact-item { margin: 0 10px; color: #4b5563; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- 2. UTILS & SERVICES ---
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

# --- 3. IA INTELLIGENTE ---
@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    client = get_ai_client()
    if not client: return None
    
    prompt = f"""
    Tu es un Expert Recrutement.
    
    TACHE:
    1. Extrais Infos + HISTORIQUE DÉTAILLÉ (Derniers postes).
    2. Analyse Skills avec NIVEAUX (Expert/Intermédiaire/Junior).
    3. Guide Entretien précis.
    
    OFFRE: {job[:2000]}
    CV: {cv_text[:3500]}
    
    JSON ATTENDU (Strict):
    {{
        "infos": {{
            "nom": "Nom", "email": "Email", "tel": "Tel", "ville": "Ville",
            "linkedin": "URL", "annees_exp": "X ans", "poste_actuel": "Titre"
        }},
        "scores": {{ "global": 0-100, "tech": 0-10, "exp": 0-10, "soft": 0-10, "culture": 0-10 }},
        "market": {{ "min": 45, "max": 55, "txt": "Justif courte" }},
        "historique": [
            {{ "titre": "Titre Poste", "entreprise": "Boite", "duree": "2020-2023", "resume": "1 phrase clé" }},
            {{ "titre": "Titre Poste 2", "entreprise": "Boite", "duree": "2018-2020", "resume": "1 phrase clé" }}
        ],
        "skills_detail": {{
            "expert": ["Skill A", "Skill B"],
            "intermediaire": ["Skill C"],
            "junior": ["Skill D"],
            "manquant": ["Skill E"]
        }},
        "analyse": {{
            "verdict": "Synthèse pro.",
            "pros": ["Atout 1", "Atout 2"],
            "cons": ["Risque 1", "Risque 2"]
        }},
        "interview": {{
            "tech": [{{ "q": "Question?", "a": "Réponse" }}],
            "soft": [{{ "q": "Question?", "a": "Réponse" }}]
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

st.title("👔 AI Recruiter PRO - V7")

with st.sidebar:
    st.header("1. Offre (AO)")
    uploaded_ao = st.file_uploader("PDF AO", type=['pdf'])
    ao_txt = st.text_area("Ou texte", height=100)
    job_desc = extract_text_from_pdf(uploaded_ao.getvalue()) if uploaded_ao else ao_txt
    
    ponderation_input = st.text_area("Critères", height=70)
    st.divider()
    st.header("2. Candidats")
    uploaded_files = st.file_uploader("CVs", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🗑️ Reset"):
        st.session_state.all_results = []
        st.rerun()
    launch_btn = st.button("⚡ Analyser")

if launch_btn and job_desc and uploaded_files:
    st.write(f"Analyse de {len(uploaded_files)} profils...")
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

# --- 5. AFFICHAGE DASHBOARD ---
if st.session_state.all_results:
    df = pd.DataFrame(st.session_state.all_results)
    df = df.sort_values('Score', ascending=False)
    
    st.subheader("📋 Liste des Candidats")
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
    st.subheader("📂 Dossiers Détaillés")

    for idx, row in df.iterrows():
        d = row['full']
        score = row['Score']
        
        # HEADER DU DOSSIER
        with st.expander(f"👤 {d['infos']['nom']} | {d['infos'].get('poste_actuel', 'N/A')} | Score: {score}%", expanded=False):
            
            # 1. BARRE CONTACT & INFO CLÉS
            st.markdown(f"""
            <div class="contact-row">
                <span class="contact-item">📧 {d['infos'].get('email')}</span>
                <span class="contact-item">📱 {d['infos'].get('tel')}</span>
                <span class="contact-item">📍 {d['infos'].get('ville')}</span>
                <span class="contact-item">💰 {d['market'].get('min')} - {d['market'].get('max')} k€ (Est.)</span>
                <span class="contact-item">🔗 <a href="{d['infos'].get('linkedin', '#')}" target="_blank">LinkedIn</a></span>
            </div>
            """, unsafe_allow_html=True)

            # LAYOUT GRILLE 2 COLONNES (2/3 Gauche, 1/3 Droite)
            col_main, col_side = st.columns([2, 1])

            # --- COLONNE PRINCIPALE (GAUCHE) ---
            with col_main:
                st.markdown("### 🧠 Analyse & Parcours")
                st.info(d['analyse']['verdict'])
                
                # PROS / CONS CÔTE À CÔTE
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**✅ Forces**")
                    for p in d['analyse']['pros']: st.markdown(f"<div class='box-pro'>{p}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown("**🚨 Vigilance**")
                    for c in d['analyse']['cons']: st.markdown(f"<div class='box-con'>{c}</div>", unsafe_allow_html=True)

                # HISTORIQUE (RETOUR DE L'INFO PERDUE)
                st.markdown("#### 📅 Expérience Professionnelle")
                if d.get('historique'):
                    for exp in d['historique']:
                        st.markdown(f"**{exp['titre']}** chez *{exp['entreprise']}* ({exp['duree']})")
                        st.caption(f"📝 {exp['resume']}")
                        st.markdown("---")
                else:
                    st.warning("Historique non détecté dans le PDF.")

                # GUIDE ENTRETIEN (INTEGRÉ EN BAS DE PAGE GAUCHE)
                st.markdown("#### 🎤 Questions Suggérées")
                for q in d['interview'].get('tech', [])[:2]: # Top 2 questions tech
                    st.write(f"**Q:** {q['q']}")
                    st.caption(f"💡 {q['a']}")
                for q in d['interview'].get('soft', [])[:2]: # Top 2 questions soft
                    st.write(f"**Q:** {q['q']}")
                    st.caption(f"💡 {q['a']}")

            # --- COLONNE LATÉRALE (DROITE) ---
            with col_side:
                st.markdown("### 📊 Métriques")
                
                # RADAR
                vals = [d['scores']['tech'], d['scores']['exp'], d['scores']['soft'], d['scores']['culture']]
                fig = go.Figure(data=go.Scatterpolar(r=vals, theta=['Tech', 'Exp', 'Soft', 'Culture'], fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=200, margin=dict(t=20, b=20, l=30, r=30))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")
                
                # COMPÉTENCES DÉTAILLÉES PAR NIVEAU
                st.markdown("#### 🛠️ Compétences")
                
                st.markdown("**🏆 Expert**")
                if d['skills_detail']['expert']:
                    for s in d['skills_detail']['expert']: st.markdown(f"<span class='badge-expert'>{s}</span>", unsafe_allow_html=True)
                else: st.caption("Rien de notable")

                st.markdown("**⚡ Intermédiaire**")
                if d['skills_detail']['intermediaire']:
                    for s in d['skills_detail']['intermediaire']: st.markdown(f"<span class='badge-inter'>{s}</span>", unsafe_allow_html=True)
                
                st.markdown("**🌱 Junior / Notions**")
                if d['skills_detail']['junior']:
                    for s in d['skills_detail']['junior']: st.markdown(f"<span class='badge-junior'>{s}</span>", unsafe_allow_html=True)

                st.markdown("**❌ Manquants**")
                if d['skills_detail']['manquant']:
                    for s in d['skills_detail']['manquant']: st.markdown(f"<span style='color:red; font-size:0.8rem'>• {s}</span>", unsafe_allow_html=True)

elif not launch_btn:
    st.info("👈 Menu latéral : Chargez l'AO et les CVs pour démarrer.")
