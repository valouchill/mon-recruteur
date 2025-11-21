import streamlit as st
import openai
from pypdf import PdfReader
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Recruteur IA - Web", layout="wide")

# --- SÉCURITÉ (MOT DE PASSE) ---
def check_password():
    """Retourne True si l'utilisateur a le bon mot de passe."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    pwd = st.text_input("Mot de passe d'accès", type="password")
    if st.button("Se connecter"):
        # Le mot de passe est stocké dans les secrets de Streamlit
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")
    return False

if not check_password():
    st.stop()

# --- CONNEXION API (GROQ ou OPENAI) ---
# On récupère la clé API depuis les secrets sécurisés du serveur
try:
    client = openai.OpenAI(
        base_url="https://api.groq.com/openai/v1", # On utilise Groq pour la vitesse/gratuité
        api_key=st.secrets["GROQ_API_KEY"]
    )
    # Modèle : Llama3-70b (très puissant et rapide sur Groq)
    MODEL_NAME = "llama3-70b-8192"
except Exception as e:
    st.error(f"Erreur de configuration API : {e}")
    st.stop()

# --- FONCTIONS (Identiques à avant) ---

def extract_text_from_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except: return None

def scrape_job_description(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            for s in soup(["script", "style", "nav", "footer"]): s.extract()
            return soup.get_text(separator='\n')[:15000]
    except: return None
    return None

def analyze_candidate_web(job_description, candidate_text):
    system_prompt = """
    Tu es un expert RH. Analyse ce CV pour extraire les infos de contact et la pertinence.
    Réponds UNIQUEMENT avec ce JSON :
    {
        "nom_complet": "Prénom Nom",
        "email": "email@domaine.com ou Non trouvé",
        "telephone": "numéro ou Non trouvé",
        "ville": "Ville ou Non trouvé",
        "score_match": 0 à 100 (int),
        "resume_profil": "Phrase courte",
        "competences_cles": ["Skill 1", "Skill 2"],
        "point_vigilance": "Rien à signaler ou problème potentiel"
    }
    """
    user_prompt = f"POSTE : {job_description}\n\nCV CANDIDAT : {candidate_text}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return None

# --- INTERFACE WEB ---

st.title("🌍 Plateforme de Recrutement IA")
st.markdown("Dashboard de sourcing centralisé.")

col1, col2 = st.columns([1, 2])

if 'web_results' not in st.session_state:
    st.session_state.web_results = []

with col1:
    st.subheader("1. Le Besoin")
    tab_txt, tab_url = st.tabs(["Texte", "Import URL"])
    job_desc = ""
    with tab_txt:
        manual_desc = st.text_area("Description", height=200)
        if manual_desc: job_desc = manual_desc
    with tab_url:
        url_input = st.text_input("URL Offre (APEC, LinkedIn...)")
        if st.button("Aspirer le site"):
            scraped = scrape_job_description(url_input)
            if scraped:
                st.success("Contenu récupéré !")
                st.info(scraped[:200] + "...")
                job_desc = scraped # Pour l'analyse
                # On sauve dans session pour ne pas perdre si refresh
                st.session_state['scraped_desc'] = scraped
            
    # Récupération si déjà scrappé
    if 'scraped_desc' in st.session_state and not job_desc:
        job_desc = st.session_state['scraped_desc']

with col2:
    st.subheader("2. Les Candidats")
    uploaded_files = st.file_uploader("Déposez les PDF", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🚀 Lancer l'analyse Cloud", type="primary"):
        if job_desc and uploaded_files:
            progress = st.progress(0)
            res = []
            for i, file in enumerate(uploaded_files):
                txt = extract_text_from_pdf(file)
                if txt:
                    data = analyze_candidate_web(job_desc, txt)
                    if data: res.append(data)
                progress.progress((i+1)/len(uploaded_files))
            st.session_state.web_results = res
            progress.empty()

# --- RÉSULTATS ---
if st.session_state.web_results:
    st.divider()
    df = pd.DataFrame(st.session_state.web_results)
    if not df.empty:
        df = df.sort_values(by='score_match', ascending=False)
        
        st.download_button(
            "📥 Télécharger Excel",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name='sourcing_export.csv',
            mime='text/csv'
        )
        
        for _, row in df.iterrows():
            score = row['score_match']
            color = "green" if score > 75 else "orange" if score > 50 else "red"
            with st.expander(f"{row['nom_complet']} ({score}%)"):
                st.write(f"**Tel:** {row['telephone']} | **Email:** {row['email']}")
                st.info(row['resume_profil'])
