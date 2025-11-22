import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="AI Recruiter Pro", layout="wide", page_icon="🚀")

# --- 2. GESTION DES CLÉS API (SECRETS) ---
def get_ai_client():
    """Récupère le client Groq via les secrets Streamlit"""
    try:
        # Vérification de la présence de la clé
        if "GROQ_API_KEY" in st.secrets:
            api_key = st.secrets["GROQ_API_KEY"]
            return openai.OpenAI(
                base_url="https://api.groq.com/openai/v1", 
                api_key=api_key
            )
        else:
            st.error("❌ Clé GROQ_API_KEY absente des Secrets Streamlit.")
            return None
    except Exception as e:
        st.error(f"❌ Erreur de connexion API : {e}")
        return None

def save_to_google_sheet(data):
    """Sauvegarde le candidat dans Google Sheets si configuré"""
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            # Conversion de l'objet TOML en dict pour gspread
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # Ouvre le fichier nommé 'Recrutement_DB'
            sheet = client.open("Recrutement_DB").sheet1
            
            # Ajoute une ligne : Date, Nom, Score, Email, Poste
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                data['infos']['nom'], 
                f"{data['scores']['global']}%",
                data['infos']['email'],
                data['infos'].get('poste_vise', 'N/A')
            ])
    except Exception as e:
        # On ne bloque pas l'app si Google Sheets échoue, on affiche juste un warning console
        print(f"Warning Google Sheets: {e}")

def extract_text_from_pdf(file):
    """Extrait le texte brut d'un PDF"""
    try:
        reader = PdfReader(file)
        return "".join([page.extract_text() for page in reader.pages])
    except: return ""

# --- 3. CŒUR DU SYSTÈME : L'ANALYSE INTELLIGENTE ---
def analyze_candidate_deep(job, cv_text):
    client = get_ai_client()
    if not client: return None
    
    # Prompt optimisé pour la sémantique et les synonymes
    prompt = f"""
    Tu es un expert en recrutement technique (Chasseur de tête Senior). 
    Compare ce CV à cette OFFRE D'EMPLOI (AO).
    
    RÈGLES D'ANALYSE SÉMANTIQUE (TRES IMPORTANT) :
    1. Ne cherche pas les mots-clés exacts. Cherche le SENS. 
       (Ex: Si AO demande "Vente" et CV dit "Business Development", c'est un MATCH ✅).
    2. Fais les déductions techniques logiques. 
       (Ex: Si CV dit "Laravel", le candidat connait "PHP". Si "React", il connait "JS").
    3. Gère les langues : Si AO en Français et CV en Anglais, traduis et matche.
    
    OFFRE (AO) : {job[:2500]}
    CV CANDIDAT : {cv_text[:3500]}
    
    Réponds UNIQUEMENT avec ce JSON strict :
    {{
        "infos": {{
            "nom": "Prénom Nom",
            "email": "Email ou N/A",
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
            "skills_match": ["Skill A (Trouvé)", "Skill B (Déduit de...)"],
            "skills_missing": ["Skill X Manquant", "Skill Y Manquant"],
            "verdict_technique": "Phrase résumant la pertinence technique"
        }},
        "action": {{
            "questions_entretien": ["Question 1 (sur un manque)", "Question 2 (technique)"],
            "email_draft": "Brouillon d'email de premier contact personnalisé."
        }}
    }}
    """
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        st.error(f"Erreur lors de l'analyse IA : {e}")
        return None

# --- 4. INTERFACE UTILISATEUR (FRONTEND) ---

st.title("🚀 AI Recruiter Dashboard")
st.markdown("Analyse sémantique, détection de synonymes & Scoring.")

# Barre latérale
with st.sidebar:
    st.header("1. Le Besoin (AO)")
    job_desc = st.text_area("Collez l'offre d'emploi ici", height=300, placeholder="Ex: Développeur Fullstack, 5 ans exp, Python/React...")
    
    st.divider()
    st.header("2. Les Candidats")
    uploaded_files = st.file_uploader("PDF uniquement", type=['pdf'], accept_multiple_files=True)
    
    launch_btn = st.button("⚡ Lancer l'Analyse", type="primary")
    st.caption("Powered by Groq (Llama3) & Streamlit")

# Zone Principale
if launch_btn and job_desc and uploaded_files:
    
    st.write(f"🔄 Analyse en cours de {len(uploaded_files)} dossiers...")
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        # Extraction
        text_cv = extract_text_from_pdf(file)
        
        if text_cv:
            # Appel IA
            data = analyze_candidate_deep(job_desc, text_cv)
            
            if data:
                # Sauvegarde Cloud
                save_to_google_sheet(data)

                # --- AFFICHAGE CARTE CANDIDAT ---
                score = data['scores']['global']
                # Couleur dynamique
                color = "green" if score >= 75 else "orange" if score >= 50 else "red"
                
                with st.expander(f"👤 **{data['infos']['nom']}** - Match : :{color}[{score}%]", expanded=True):
                    
                    # En-tête
                    col_info1, col_info2, col_info3 = st.columns(3)
                    col_info1.write(f"📅 **Expérience:** {data['infos']['annees_exp']}")
                    col_info2.write(f"📧 **Email:** {data['infos']['email']}")
                    col_info3.write(f"📱 **Tel:** {data['infos']['tel']}")
                    
                    st.info(f"🧠 **Verdict:** {data['analyse_skills']['verdict_technique']}")
                    
                    st.divider()
                    
                    # Colonnes : Graphique vs Compétences
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
                        st.subheader("Analyse des Écarts")
                        
                        # Badges Verts (Trouvés ou Déduits)
                        st.write("✅ **Forces & Correspondances :**")
                        matches_html = "".join([f"<span style='background:#d4edda; color:#155724; padding:5px 10px; border-radius:15px; margin:2px; display:inline-block; font-size:0.9em'>{s}</span>" for s in data['analyse_skills']['skills_match']])
                        st.markdown(matches_html, unsafe_allow_html=True)
                        
                        st.write("") # Espace
                        
                        # Badges Rouges (Manquants)
                        st.write("❌ **Points manquants (Gaps) :**")
                        misses_html = "".join([f"<span style='background:#f8d7da; color:#721c24; padding:5px 10px; border-radius:15px; margin:2px; display:inline-block; font-size:0.9em'>{s}</span>" for s in data['analyse_skills']['skills_missing']])
                        st.markdown(misses_html, unsafe_allow_html=True)

                    # Onglets d'Action
                    st.divider()
                    t1, t2 = st.tabs(["🎤 Préparer l'entretien", "✉️ Brouillon d'Email"])
                    
                    with t1:
                        st.write("Questions suggérées par l'IA :")
                        for q in data['action']['questions_entretien']:
                            st.markdown(f"- {q}")
                    
                    with t2:
                        st.text_area("Copier le message", value=data['action']['email_draft'], height=150)

        # Mise à jour barre de progression
        progress_bar.progress((i + 1) / len(uploaded_files))
        
    progress_bar.empty()
    st.success("✅ Analyse terminée avec succès !")

elif launch_btn:
    st.warning("⚠️ Veuillez ajouter une description de poste ET des fichiers PDF.")

