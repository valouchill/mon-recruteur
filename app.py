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
st.set_page_config(page_title="AI Recruiter PRO - V3.0", layout="wide", page_icon="👑")

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
                poste_ao
            ])
    except Exception as e:
        # On log juste l'erreur sans bloquer l'app
        print(f"Warning Google Sheets: {e}")

# --- AMÉLIORATION 1 : CACHING & PDF ---
@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes):
    """Extrait le texte brut d'un PDF (Version Cachée)"""
    try:
        # On utilise io.BytesIO car st.file_uploader renvoie un objet qui peut être fermé
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
        return text
    except: return ""

# --- 3. CŒUR DU SYSTÈME : L'ANALYSE INTELLIGENTE ---

# --- AMÉLIORATION 2 : CACHING & RETRY ---
@st.cache_data(ttl=3600, show_spinner=False)
def analyze_candidate_deep(job, cv_text, ponderation):
    """Analyse IA avec cache d'une heure"""
    client = get_ai_client()
    if not client: return None
    
    ponderation_instruction = f"""
    RÈGLES DE SCORING PONDÉRÉ :
    Si la pondération suivante est fournie, tu dois ajuster le score global (global) pour donner plus d'importance aux mots-clés :
    {ponderation if ponderation else 'PAS DE PONDÉRATION SPÉCIFIQUE. Utilise un scoring équilibré.'}
    """
    
    # --- AMÉLIORATION 3 : PROMPT OPTIMISÉ (CHAIN-OF-THOUGHT) ---
    prompt = f"""
    Tu es un Chasseur de tête Senior. RAISONNE ÉTAPE PAR ÉTAPE :

    ÉTAPE 1 - Extraction des faits bruts :
    - Liste les compétences explicitement mentionnées dans le CV.
    - Identifie les durées exactes de chaque poste.

    ÉTAPE 2 - Déduction sémantique :
    - Pour chaque compétence de l'AO, cherche des synonymes/équivalents dans le CV.
    - Exemple : "Kubernetes" peut être déduit de "orchestration de conteneurs Docker en production".

    ÉTAPE 3 - Analyse des "Red Flags" :
    - Trous inexpliqués (> 6 mois).
    - Job hopping (changements fréquents < 1 an).
    - Incohérence Titre vs Expérience réelle.

    Compare ce CV à cette OFFRE D'EMPLOI (AO) et génère le JSON final.

    {ponderation_instruction}
    
    OFFRE (AO) : {job[:2500]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict et complet :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
            "tel": "Tel ou N/A",
            "annees_exp": "X ans (estimé)",
            "poste_vise": "Titre du poste deviné"
        }},
        "scores": {{
            "global": 0-100 (Ajusté par la pondération),
            "tech_hard_skills": 0-10,
            "experience": 0-10,
            "soft_skills": 0-10,
            "fit_culturel": 0-10
        }},
        "analyse_skills": {{
            "competences_matchees": [
                {{"nom": "Compétence", "niveau": "Junior/Intermédiaire/Expert", "source": "Détail de la déduction"}}
            ],
            "skills_missing": ["Skill X Manquant", "Skill Y Manquant"],
            "verdict_technique": "Phrase résumant la pertinence technique."
        }},
        "historique": [
            {{"titre": "Poste 1 (Le plus récent)", "duree": "X ans", "periode": "YYYY-YYYY"}},
            {{"titre": "Poste 2", "duree": "X ans", "periode": "YYYY-YYYY"}}
        ],
        "comparatif": {{
            "points_forts": ["Force 1", "Force 2"],
            "points_faibles": ["Faible 1 (Red Flag ou Gap majeur)", "Faible 2"]
        }},
        "action": {{
            "questions_entretien": ["Question 1", "Question 2"],
            "email_draft": "Brouillon d'email."
        }}
    }}
    """
    
    # Logique de Retry
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
                st.error(f"❌ Erreur IA après {max_retries} essais : {e}")
                return None
            time.sleep(1) # Attente courte avant retry

# --- 4. INTERFACE UTILISATEUR (FRONTEND) ---

# --- AMÉLIORATION 4 : SESSION STATE ---
if 'all_results' not in st.session_state:
    st.session_state.all_results = []

st.title("👑 AI Recruiter PRO - V3.0")
st.markdown("Analyse de la finesse du match, Niveaux de compétences et Red Flags.")

# Barre latérale (Inputs)
with st.sidebar:
    st.header("1. Le Besoin (AO)")
    job_desc = st.text_area("Collez l'offre d'emploi ici", height=200, placeholder="Ex: Développeur Fullstack, 5 ans exp, Python/React...")
    
    st.subheader("Pondération (Avancé)")
    ponderation_input = st.text_area(
        "Poids des compétences (Optionnel)",
        height=100,
        placeholder="Ex:\nPython: 50%\nAWS: 30%\nSoft Skills: 20%",
        help="Ajuste le score global. Si vide, le score est équilibré."
    )
    
    st.divider()
    st.header("2. Les Candidats")
    uploaded_files = st.file_uploader("PDF uniquement", type=['pdf'], accept_multiple_files=True)
    
    # Bouton de reset
    if st.button("🗑️ Réinitialiser l'analyse"):
        st.session_state.all_results = []
        st.rerun()

    launch_btn = st.button("⚡ Lancer l'Analyse", type="primary")
    
    # --- AMÉLIORATION 5 : MÉTRIQUES EN TEMPS RÉEL ---
    if st.session_state.all_results:
        st.divider()
        st.subheader("📊 Synthèse Session")
        df_metrics = pd.DataFrame(st.session_state.all_results)
        st.metric("Candidats traités", len(df_metrics))
        st.metric("Score Moyen", f"{df_metrics['Score (%)'].mean():.1f}%")

# Zone Principale (Résultats)
if launch_btn and job_desc and uploaded_files:
    
    if len(uploaded_files) > 20:
        st.error("⚠️ Maximum 20 CV par lot pour des raisons de performance.")
    else:
        st.write(f"🔄 Analyse en cours de {len(uploaded_files)} dossier(s)...")
        progress_bar = st.progress(0)
        
        # On vide les résultats précédents si nouvelle analyse lancée
        # (Ou on peut choisir d'ajouter, ici je choisis de remplacer pour simplifier le flux)
        current_batch_results = []
        
        # Boucle d'analyse
        for i, file in enumerate(uploaded_files):
            # Lecture des bytes pour le cache
            file_bytes = file.getvalue()
            text_cv = extract_text_from_pdf(file_bytes)
            
            if text_cv:
                # Appel de l'IA (Caché)
                data = analyze_candidate_deep(job_desc, text_cv, ponderation_input)
                
                if data:
                    save_to_google_sheet(data, job_desc)

                    red_flags_list = [f for f in data['comparatif']['points_faibles'] if 'red flag' in f.lower()]
                    first_red_flag = red_flags_list[0] if red_flags_list else "Rien de critique"
                    
                    # Structure aplatie pour le tableau et l'affichage
                    result_entry = {
                        'Nom': data['infos']['nom'],
                        'Score (%)': int(data['scores']['global']),
                        'Exp. (ans)': data['infos']['annees_exp'],
                        'Verdict': data['analyse_skills']['verdict_technique'],
                        'Red Flag Principal': first_red_flag,
                        'Email': data['infos']['email'],
                        'full_data': data # On garde tout le JSON pour l'affichage détaillé
                    }
                    
                    current_batch_results.append(result_entry)

            # Mise à jour barre de progression
            progress_bar.progress((i + 1) / len(uploaded_files))
        
        # Mise à jour du Session State
        st.session_state.all_results = current_batch_results
        progress_bar.empty()
        st.success("✅ Analyse terminée !")
        st.rerun() # Rerun pour afficher proprement les résultats stockés

# --- 5. AFFICHAGE DES RÉSULTATS (DEPUIS LE SESSION STATE) ---
if st.session_state.all_results:
    
    # Conversion en DF pour manipulation
    df = pd.DataFrame(st.session_state.all_results)
    
    # --- AMÉLIORATION 6 : FILTRES ---
    col_filter1, col_filter2 = st.columns([1, 3])
    with col_filter1:
        min_score = st.slider("Filtrer par Score min (%)", 0, 100, 0)
    
    # Filtrage
    df_filtered = df[df['Score (%)'] >= min_score].sort_values(by='Score (%)', ascending=False)
    
    # Tableau global
    st.header("📊 Tableau Comparatif")
    st.dataframe(
        df_filtered.drop(columns=['full_data']), # On cache la grosse colonne JSON
        use_container_width=True, 
        hide_index=True
    )

    # --- AMÉLIORATION 7 : EXPORT CSV ---
    csv = df_filtered.drop(columns=['full_data']).to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Télécharger le rapport CSV",
        data=csv,
        file_name='analyse_candidats.csv',
        mime='text/csv',
    )
    
    st.divider()
    st.header("👤 Détail des Candidats")

    # Affichage des cartes détaillées (uniquement pour les filtrés)
    for index, row in df_filtered.iterrows():
        data = row['full_data'] # Récupération du JSON complet
        score = row['Score (%)']
        color = "green" if score >= 75 else "blue" if score >= 60 else "orange" if score >= 40 else "red"
        
        with st.expander(f"**{data['infos']['nom']}** - Match: :{color}[{score}%] - {data['infos']['poste_vise']}", expanded=False):
            
            # EN-TÊTE
            c_info1, c_info2 = st.columns([2, 1])
            with c_info1:
                st.info(f"🧠 **Verdict:** {data['analyse_skills']['verdict_technique']}")
                if data['comparatif']['points_faibles']:
                    st.markdown("🚩 **Alertes (Red Flags) :**")
                    for f in data['comparatif']['points_faibles']:
                        st.error(f"- {f}")
            with c_info2:
                st.subheader("Historique")
                for item in data['historique']:
                        st.markdown(f"**{item.get('titre', 'N/A')}**")
                        st.caption(f"{item.get('periode', 'N/A')} ({item.get('duree', 'N/A')})")
            
            st.divider()

            # GRAPHIQUE & SKILLS
            c_graph, c_skills = st.columns([1, 2])
            with c_graph:
                categories = ['Tech', 'Expérience', 'Soft Skills', 'Culture']
                values = [data['scores']['tech_hard_skills'], data['scores']['experience'], data['scores']['soft_skills'], data['scores']['fit_culturel']]
                fig = go.Figure(data=go.Scatterpolar(r=values, theta=categories, fill='toself', name=data['infos']['nom']))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=250, margin=dict(t=20, b=20, l=40, r=40))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{index}_{data['infos']['nom']}")
                
            with c_skills:
                st.subheader("Compétences Clés")
                # Affichage en colonnes compactes
                cols_skills = st.columns(3)
                for idx, comp in enumerate(data['analyse_skills']['competences_matchees']):
                    with cols_skills[idx % 3]:
                        niveau_lower = comp.get('niveau', '').lower()
                        color_badge = "green" if "expert" in niveau_lower else "blue" if "intermédiaire" in niveau_lower else "orange"
                        st.markdown(f":{color_badge}[**{comp['nom']}**] ({comp['niveau']})")
                
                st.markdown("---")
                st.write("❌ **Gaps / Manquants :**")
                misses_html = "".join([f"<span style='background:#ffebee; color:#c62828; padding:4px 8px; border-radius:4px; margin:2px; display:inline-block; font-size:0.85em'>{s}</span>" for s in data['analyse_skills']['skills_missing']])
                st.markdown(misses_html, unsafe_allow_html=True)

            # ACTIONS
            st.divider()
            t1, t2 = st.tabs(["📧 Action Rapide", "🎤 Guide d'Entretien"])
            with t1:
                st.text_area("Brouillon d'email", value=data['action']['email_draft'], height=100, key=f"email_{index}")
            with t2:
                for q in data['action']['questions_entretien']:
                    st.markdown(f"- ❓ {q}")

elif not launch_btn and not st.session_state.all_results:
    st.info("👈 Commencez par ajouter une offre et des CVs dans la barre latérale.")

