import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="AI Recruiter PRO - V2.0", layout="wide", page_icon="👑")

# --- 2. GESTION DES CLÉS API (SECRETS) ---
def get_ai_client():
    """Récupère le client Groq via les secrets Streamlit"""
    try:
        if "GROQ_API_KEY" in st.secrets:
            return openai.OpenAI(
                base_url="https://api.groq.com/openai/v1", 
                api_key=st.secrets["GROQ_API_KEY"]
            )
        return None
    except: return None

def save_to_google_sheet(data, job_desc):
    """Sauvegarde le candidat dans Google Sheets si configuré"""
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            
            # Utilisation du nom de l'AO pour référence
            poste_ao = job_desc.split('\n')[0][:50]
            
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                data['infos']['nom'], 
                f"{data['scores']['global']}%",
                data['infos']['email'],
                poste_ao
            ])
    except Exception as e:
        print(f"Warning Google Sheets: {e}")

def extract_text_from_pdf(file):
    """Extrait le texte brut d'un PDF"""
    try:
        reader = PdfReader(file)
        return "".join([page.extract_text() for page in reader.pages])
    except: return ""

# --- 3. CŒUR DU SYSTÈME : L'ANALYSE INTELLIGENTE ---
def analyze_candidate_deep(job, cv_text, ponderation):
    client = get_ai_client()
    if not client: return None
    
    # Intégration de la pondération dans le prompt
    ponderation_instruction = f"""
    RÈGLES DE SCORING PONDÉRÉ :
    Si la pondération suivante est fournie, tu dois ajuster le score global (global) pour donner plus d'importance aux mots-clés :
    {ponderation if ponderation else 'PAS DE PONDÉRATION SPÉCIFIQUE. Utilise un scoring équilibré.'}
    """
    
    # Prompt ultra-détaillé
    prompt = f"""
    Tu es un Chasseur de tête Senior, spécialiste de l'analyse sémantique.
    Compare ce CV à cette OFFRE D'EMPLOI (AO) et estime la finesse du match.
    
    RÈGLES D'ANALYSE ET D'EXTRACTION :
    1. Niveau de Compétence : Pour chaque compétence matcheée, assigne un niveau (Junior, Intermédiaire, Expert).
    2. Analyse Sémantique : Utilise les synonymes, les déductions logiques (ex: 'Django' implique 'Python') et gère les acronymes/langues.
    3. Historique : Extrais la chronologie des 3 derniers postes du candidat.
    4. Red Flags : Les points faibles dans 'comparatif/points_faibles' doivent inclure des alertes sur le CV (ex: 'job-hopping', 'trous de 1 an', 'manque d'expérience managériale').

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
            "global": 0-100 (Ajusté par la pondération si présente),
            "tech_hard_skills": 0-10,
            "experience": 0-10,
            "soft_skills": 0-10,
            "fit_culturel": 0-10
        }},
        "analyse_skills": {{
            "competences_matchees": [
                {{"nom": "Compétence", "niveau": "Junior/Intermédiaire/Expert", "source": "Commentaire de déduction (ex: 5 ans, ou déduit de Framework X)"}}
            ],
            "skills_missing": ["Skill X Manquant", "Skill Y Manquant"],
            "verdict_technique": "Phrase résumant la pertinence technique."
        }},
        "historique": [
            {{"titre": "Poste 1 (Le plus récent)", "duree": "X ans", "periode": "YYYY-YYYY"}},
            {{"titre": "Poste 2", "duree": "X ans", "periode": "YYYY-YYYY"}}
        ],
        "comparatif": {{
            "points_forts": ["Force 1 (Lien direct avec l'AO)", "Force 2"],
            "points_faibles": ["Faible 1 (Red Flag ou Gap majeur)", "Faible 2"]
        }},
        "action": {{
            "questions_entretien": ["Question 1 (sur une faiblesse de niveau)", "Question 2 (technique avancée)"],
            "email_draft": "Brouillon d'email de premier contact personnalisé."
        }}
    }}
    """
    
    try:
        res = client.chat.completions.create(
            # Utilisation du modèle le plus récent
            model="llama-3.3-70b-versatile", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        st.error(f"❌ Erreur lors de l'analyse IA. Vérifiez le modèle Groq: {e}")
        return None

# --- 4. INTERFACE UTILISATEUR (FRONTEND) ---

st.title("👑 AI Recruiter PRO Dashboard")
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
        help="Permet d'ajuster le score global. Si vide, le score est équilibré."
    )
    
    st.divider()
    st.header("2. Les Candidats")
    uploaded_files = st.file_uploader("PDF uniquement", type=['pdf'], accept_multiple_files=True)
    
    launch_btn = st.button("⚡ Lancer l'Analyse", type="primary")
    st.caption("Propulsé par Groq (Llama 3.3) & Streamlit")

# Zone Principale (Résultats)
if launch_btn and job_desc and uploaded_files:
    
    st.write(f"🔄 Analyse en cours de {len(uploaded_files)} dossier(s)...")
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        text_cv = extract_text_from_pdf(file)
        
        if text_cv:
            # Appel IA avec pondération
            data = analyze_candidate_deep(job_desc, text_cv, ponderation_input)
            
            if data:
                # Sauvegarde Cloud
                save_to_google_sheet(data, job_desc)

                # --- AFFICHAGE CARTE CANDIDAT ---
                score = data['scores']['global']
                color = "green" if score >= 75 else "blue" if score >= 60 else "orange" if score >= 40 else "red"
                
                with st.expander(f"👤 **{data['infos']['nom']}** - Match: :{color}[{score}%] - {data['infos']['poste_vise']}", expanded=True):
                    
                    # 1. EN-TÊTE D'INFO & RED FLAGS
                    c_info1, c_info2 = st.columns([2, 1])
                    
                    with c_info1:
                        st.info(f"🧠 **Verdict:** {data['analyse_skills']['verdict_technique']}")
                        
                        # RED FLAGS (NOUVEAUTÉ)
                        if data['comparatif']['points_faibles']:
                            st.markdown("🚩 **Alertes (Red Flags / Points Faibles) :**")
                            for f in data['comparatif']['points_faibles']:
                                st.error(f"- {f}", icon="🚨")

                    with c_info2:
                        st.subheader("Historique des Postes")
                        # HISTORIQUE (NOUVEAUTÉ)
                        for item in data['historique']:
                             st.markdown(f"**{item.get('titre', 'N/A')}** ({item.get('duree', 'N/A')})")
                             st.caption(f"Période: {item.get('periode', 'N/A')}")
                    
                    st.divider()

                    # 2. COLONNES PRINCIPALES : GRAPH + NIVEAUX DE SKILLS
                    c_graph, c_skills = st.columns([1, 2])
                    
                    with c_graph:
                        # Radar Chart
                        categories = ['Tech', 'Expérience', 'Soft Skills', 'Culture']
                        values = [
                            data['scores']['tech_hard_skills'],
                            data['scores']['experience'],
                            data['scores']['soft_skills'],
                            data['scores']['fit_culturel']
                        ]
                        fig = go.Figure(data=go.Scatterpolar(r=values, theta=categories, fill='toself', name=data['infos']['nom']))
                        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), height=220, margin=dict(t=20, b=20, l=30, r=30))
                        st.plotly_chart(fig, use_container_width=True)
                        
                    with c_skills:
                        st.subheader("Détail des Compétences & Niveaux")
                        
                        # AFFICHAGE DES NIVEAUX DE COMPÉTENCE (NOUVEAUTÉ)
                        if data['analyse_skills']['competences_matchees']:
                            for comp in data['analyse_skills']['competences_matchees']:
                                # Assigner une couleur basée sur le niveau
                                niveau_lower = comp.get('niveau', '').lower()
                                niveau_color = "green" if "expert" in niveau_lower else "blue" if "intermédiaire" in niveau_lower else "orange"
                                
                                st.markdown(f"**{comp['nom']}** : :{niveau_color}[{comp['niveau']}]")
                                st.caption(f"Source: {comp['source']}")
                        
                        st.markdown("---") 
                        
                        # Badges Rouges (Manquants)
                        st.write("❌ **Compétences Vraiment Manquantes (Gaps) :**")
                        misses_html = "".join([f"<span style='background:#f8d7da; color:#721c24; padding:5px 10px; border-radius:15px; margin:2px; display:inline-block; font-size:0.9em'>{s}</span>" for s in data['analyse_skills']['skills_missing']])
                        st.markdown(misses_html, unsafe_allow_html=True)

                    # Onglets d'Action
                    st.divider()
                    t1, t2, t3 = st.tabs(["📞 Contact", "🎤 Préparer l'entretien", "📧 Brouillon d'Email"])
                    
                    with t1:
                         st.markdown(f"**Email:** {data['infos']['email']} | **Téléphone:** {data['infos']['tel']}")

                    with t2:
                        st.subheader("Questions ciblées sur les Faiblesses de Niveau")
                        for q in data['action']['questions_entretien']:
                            st.markdown(f"- ❓ {q}")
                    
                    with t3:
                        st.text_area("Copier le message", value=data['action']['email_draft'], height=150)

        # Mise à jour barre de progression
        progress_bar.progress((i + 1) / len(uploaded_files))
        
    progress_bar.empty()
    st.success("✅ Analyse terminée avec succès ! La version PRO est en ligne.")

elif launch_btn:
    st.warning("⚠️ Veuillez ajouter une description de poste ET des fichiers PDF.")
