import streamlit as st
import openai
from pypdf import PdfReader
import json
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
st.set_page_config(page_title="Debug Mode", layout="wide")
st.title("🚧 Mode Diagnostic")

# --- FONCTIONS ---
def get_ai_client():
    # TEST API KEY
    try:
        if "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" in st.secrets:
            key = st.secrets["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"]
            # Vérif simple : est-ce qu'elle commence bien ?
            if not key.startswith("gsk_"):
                st.error("❌ La clé GROQ ne commence pas par 'gsk_'. Vérifiez les Secrets.")
                return None
            return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)
        else:
            st.error("❌ Clé GROQ_API_KEY introuvable dans les secrets.")
            return None
    except Exception as e:
        st.error(f"❌ Erreur création client AI: {e}")
        return None

def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"❌ Erreur lecture PDF {file.name}: {e}")
        return None

def save_to_google_sheet(data):
    # TEST GOOGLE
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ Pas de secrets Google trouvés. Sauvegarde ignorée.")
            return
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        sheet.append_row([datetime.datetime.now().strftime("%Y-%m-%d"), data['infos']['nom'], "Test Debug"])
        st.success("✅ Sauvegarde Google réussie !")
    except Exception as e:
        st.error(f"❌ Erreur Google Sheets : {e}")
        st.info("💡 Astuce : Avez-vous activé 'Google Sheets API' dans la console Google Cloud ?")

def analyze_candidate(job, cv_text):
    client = get_ai_client()
    if not client: return None
    
    prompt = f"""Analyse ce CV pour ce JOB. JSON uniquement:
    {{ "infos": {{ "nom": "Nom" }}, "analyse": {{ "score_global": 85, "verdict": "Ok" }} }}
    JOB: {job}
    CV: {cv_text[:2000]}"""
    
    try:
        res = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        st.error(f"❌ Erreur Appel IA : {e}")
        return None

# --- INTERFACE ---
col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Besoin")
    job_desc = st.text_area("Poste", "Développeur Python Senior")

with col2:
    st.header("2. Upload")
    files = st.file_uploader("CVs", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🚀 LANCER LE TEST"):
        st.write("... Démarrage du script ...")
        
        if not files:
            st.error("⚠️ Aucun fichier envoyé.")
        
        for f in files:
            st.write(f"➡️ Analyse de **{f.name}**...")
            
            # 1. TEXTE
            txt = extract_text_from_pdf(f)
            if txt:
                st.write(f"   ✅ Texte extrait ({len(txt)} caractères)")
                
                # 2. IA
                data = analyze_candidate(job_desc, txt)
                if data:
                    st.success(f"   ✅ IA Réponse reçue : {data['infos']['nom']}")
                    
                    # 3. GOOGLE
                    save_to_google_sheet(data)
                else:
                    st.error("   ❌ L'IA n'a pas répondu.")
            else:
                st.error("   ❌ Impossible de lire le texte.")
