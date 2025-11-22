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

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="AI Recruiter PRO - V4.0", layout="wide", page_icon="🚀")

# --- 2. GESTION DES CLÉS API (SECRETS) ---
def get_ai_client():
    """Récupère le client Groq via les secrets Streamlit"""
    try:
        if "GROQ_API_KEY" in st.secrets:
            api_key = st.secrets["GROQ_API_KEY"]
            return openai.OpenAI(
                base_url="https://api.groq.com/openai/v1", 
                api_key=api_key
            )
        return None
    except Exception as e:
        st.error(f"❌ Erreur de connexion API : {e}")
        return None

def save_to_google_sheet(data, job_desc):
    """Sauvegarde le candidat dans Google Sheets si configuré"""
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            
            poste_ao = job_desc.split('\n')[0][:50]
            
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                data['infos']['nom'], 
                f"{data['scores']['global']}%",
                data['infos']['email'],
                data['infos'].get('linkedin', 'N/A'), # Ajout LinkedIn
                poste_ao
            ])
    except Exception as e:
        print(f"Warning Google Sheets: {e}")

# --- CACHING & PDF ---
@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes):
    """Extrait le texte brut d'un PDF (Version Cachée)"""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
        return text
    except: return ""

# --- 3. CŒUR DU SYSTÈME : L'ANALYSE INTELLIGENTE ---

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    """Analyse IA avec cache d'une heure"""
    client = get_ai_client()
    if not client: return None
    
    ponderation_instruction = f"""
    RÈGLES DE SCORING PONDÉRÉ :
    Si la pondération suivante est fournie, tu dois ajuster le score global pour respecter ces priorités :
    {ponderation if ponderation else 'PAS DE PONDÉRATION SPÉCIFIQUE. Utilise un scoring équilibré.'}
    """
    
    # Prompt mis à jour pour extraire LinkedIn
    prompt = f"""
    Tu es un Chasseur de tête Senior.
    
    OBJECTIF :
    1. Analyser le match entre le CV et l'AO.
    2. Extraire les données de contact incluant le LIEN LINKEDIN.
    
    PROCESSUS :
    1. Cherche explicitement une URL LinkedIn dans le texte (http...linkedin.com...). Si trouvée, mets-la dans infos.linkedin.
    2. Estime le niveau d'expérience et les compétences.
    3. Identifie les Red Flags.

    {ponderation_instruction}
    
    OFFRE (AO) : {job[:2500]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
            "linkedin": "URL complète ou N/A", 
            "tel": "Tel ou N/A",
            "annees_exp": "X ans (estimé)",
            "poste_vise": "Titre du poste deviné"
        }},
        "scores": {{
            "global": 0-100,
            "tech_hard_skills": 0-10,
            "experience": 0-10,
            "soft_skills": 0-10,
            "fit_culturel": 0-10
        }},
        "analyse_skills": {{
            "competences_matchees": [
                {{"nom": "Compétence", "niveau": "Junior/Intermédiaire/Expert", "source": "Détail"}}
            ],
            "skills_missing": ["Skill X", "Skill Y"],
            "verdict_technique": "Résumé court."
        }},
        "historique": [
            {{"titre": "Poste", "duree": "X ans", "periode": "YYYY-YYYY"}}
        ],
        "comparatif": {{
            "points_forts": ["Force 1", "Force 2"],
            "points_faibles": ["Faible 1", "Faible 2"]
        }},
        "action": {{
            "questions_entretien": ["Q1", "Q2"],
            "email_draft": "Brouillon court."
        }}
    }}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"❌ Erreur IA : {e}")
                return None
            time.sleep(1)

# --- 4. INTERFACE UTILISATEUR (FRONTEND) ---

if 'all_results' not in st.session_state:
    st.session_state.all_results = []

st.title("🚀 AI Recruiter PRO - V4.0")

# Barre latérale
with st.sidebar:
    st.header("1. Le Besoin (AO)")
    
    # NOUVEAU : Upload de l'AO
    uploaded_ao = st.file_uploader("📄 Télécharger l'AO (PDF)", type=['pdf'])
    ao_text_area = st.text_area("Ou collez le texte ici", height=150, placeholder="Ex: Développeur Fullstack...")
    
    # Logique de sélection de l'AO
    job_desc = ""
    if uploaded_ao:
        with st.spinner("Lecture de l'AO..."):
            job_desc = extract_text_from_pdf(uploaded_ao.getvalue())
            st.success("AO chargée depuis le PDF !")
    elif ao_text_area:
        job_desc = ao_text_area

    st.subheader("Pondération")
    ponderation_input = st.text_area("Poids (Optionnel)", height=80, placeholder="Python: 50%\nExp: 30%")
    
    st.divider()
    st.header("2. Les Candidats")
    uploaded_files = st.file_uploader("CVs (PDF)", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🗑️ Reset Session"):
        st.session_state.all_results = []
        st.rerun()

    launch_btn = st.button("⚡ Lancer l'Analyse", type="primary")
    
    if st.session_state.all_results:
        st.divider()
        st.metric("Candidats", len(st.session_state.all_results))

# Zone Principale
if launch_btn:
    if not job_desc:
        st.error("⚠️ Veuillez fournir une Offre d'Emploi (PDF ou Texte).")
    elif not uploaded_files:
        st.error("⚠️ Veuillez charger des CVs.")
    else:
        if len(uploaded_files) > 20:
            st.warning("⚠️ Analyse limitée à 20 CVs pour la performance.")
        
        st.write(f"🔄 Analyse de {len(uploaded_files)} dossier(s)...")
        progress_bar = st.progress(0)
        current_batch = []
        
        for i, file in enumerate(uploaded_files):
            file_bytes = file.getvalue()
            text_cv = extract_text_from_pdf(file_bytes)
            
            if text_cv:
                data = analyze_candidate_deep(job_desc, text_cv, ponderation_input)
                
                if data:
                    save_to_google_sheet(data, job_desc)
                    
                    # Gestion lien LinkedIn pour affichage propre
                    lnk = data['infos'].get('linkedin', 'N/A')
                    final_link = lnk if lnk != 'N/A' and lnk.startswith('http') else None

                    result_entry = {
                        'Nom': data['infos']['nom'],
                        'Score (%)': int(data['scores']['global']),
                        'Exp.': data['infos']['annees_exp'],
                        'LinkedIn': final_link, # URL brute pour la colonne LinkColumn
                        'Verdict': data['analyse_skills']['verdict_technique'],
                        'full_data': data
                    }
                    current_batch.append(result_entry)

            progress_bar.progress((i + 1) / len(uploaded_files))
        
        st.session_state.all_results = current_batch
        progress_bar.empty()
        st.rerun()

# --- 5. RÉSULTATS ---
if st.session_state.all_results:
    
    df = pd.DataFrame(st.session_state.all_results)
    
    col_filter1, col_filter2 = st.columns([1, 3])
    with col_filter1:
        min_score = st.slider("Filtrer par Score (%)", 0, 100, 0)
    
    df_filtered = df[df['Score (%)'] >= min_score].sort_values(by='Score (%)', ascending=False)
    
    st.subheader("📊 Tableau Comparatif")
    
    # Affichage avec configuration de colonne pour le LIEN LINKEDIN
    st.dataframe(
        df_filtered.drop(columns=['full_data']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "LinkedIn": st.column_config.LinkColumn(
                "Profil LinkedIn",
                help="Cliquez pour ouvrir le profil",
                validate="^https://.*",
                display_text="Voir Profil" # Affiche "Voir Profil" au lieu de l'URL moche
            ),
            "Score (%)": st.column_config.ProgressColumn(
                "Match",
                format="%d%%",
                min_value=0,
                max_value=100,
            ),
        }
    )

    # Export CSV
    csv = df_filtered.drop(columns=['full_data']).to_csv(index=False).encode('utf-8')
    st.download_button("📥 CSV", csv, 'analyse.csv', 'text/csv')
    
    st.divider()
    st.header("👤 Détail des Candidats")

    for index, row in df_filtered.iterrows():
        data = row['full_data']
        score = row['Score (%)']
        color = "green" if score >= 75 else "blue" if score >= 60 else "orange"
        
        # Expander
        with st.expander(f"**{data['infos']['nom']}** - :{color}[{score}%]", expanded=False):
            
            # Header Carte
            c1, c2 = st.columns([3, 1])
            with c1:
                st.info(f"🧠 {data['analyse_skills']['verdict_technique']}")
                # Lien LinkedIn direct dans la carte aussi
                if row['LinkedIn']:
                    st.markdown(f"🔗 [**Voir le profil LinkedIn de {data['infos']['nom']}**]({row['LinkedIn']})")
            
            with c2:
                st.caption("Red Flags détectés:")
                if data['comparatif']['points_faibles']:
                    for f in data['comparatif']['points_faibles']:
                        if "red flag" in f.lower() or "faible" in f.lower():
                            st.error(f"{f}")
                        else:
                            st.warning(f"{f}")
            
            st.divider()
            
            # Radar & Skills
            c_graph, c_skills = st.columns([1, 2])
            with c_graph:
                categories = ['Tech', 'Exp', 'Soft', 'Culture']
                values = [
                    data['scores']['tech_hard_skills'], 
                    data['scores']['experience'], 
                    data['scores']['soft_skills'], 
                    data['scores']['fit_culturel']
                ]
                fig = go.Figure(data=go.Scatterpolar(r=values, theta=categories, fill='toself'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=250, margin=dict(t=20, b=20, l=40, r=40))
                
                # CORRECTION ID UNIQUE PLOTLY
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{index}_{data['infos']['nom']}")

            with c_skills:
                st.write("**Compétences Clés :**")
                badges = ""
                for comp in data['analyse_skills']['competences_matchees']:
                    color_b = "green" if "expert" in comp.get('niveau','').lower() else "blue"
                    badges += f"<span style='color:{color_b}; font-weight:bold; border:1px solid {color_b}; padding:2px 6px; border-radius:4px; margin-right:5px'>{comp['nom']} ({comp.get('niveau','?')})</span>"
                st.markdown(badges, unsafe_allow_html=True)
                
                if data['analyse_skills']['skills_missing']:
                    st.write("**Manquants :**")
                    st.markdown(", ".join([f"`{s}`" for s in data['analyse_skills']['skills_missing']]))

elif not launch_btn and not st.session_state.all_results:
    st.info("👈 Ajoutez l'AO (PDF/Texte) et les CVs pour commencer.")
