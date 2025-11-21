import streamlit as st
import openai
from pypdf import PdfReader
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.graph_objects as go
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
st.set_page_config(page_title="AI Headhunter", layout="wide")

# --- FONCTIONS SECRÈTES (API & DB) ---
def get_ai_client():
    try:
        return openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=st.secrets["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"]
        )
    except: return None

def save_to_google_sheet(data):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        sheet = client.open("Recrutement_DB").sheet1
        sheet.append_row([
            datetime.datetime.now().strftime("%Y-%m-%d"),
            data['infos']['nom'],
            data['infos']['email'],
            data['analyse']['score_global']
        ])
    except Exception as e: st.error(f"Erreur Google Sheet: {e}")

# --- FONCTIONS MÉTIER ---
def extract_text_from_pdf(file):
    try:
        return "".join([p.extract_text() for p in PdfReader(file).pages])
    except: return ""

def analyze_candidate(job, cv_text):
    client = get_ai_client()
    if not client: return None
    
    prompt = f"""
    Analyse ce CV pour ce JOB. Réponds UNIQUEMENT ce JSON :
    {{
        "infos": {{ "nom": "Nom", "email": "Email", "tel": "Tel" }},
        "analyse": {{ 
            "score_global": 0-100 (int), 
            "verdict": "Phrase courte",
            "points_forts": ["A", "B"],
            "manques": ["X", "Y"]
        }},
        "radar": {{ "Technique": int 0-10, "Expérience": int, "SoftSkills": int }}
    }}
    JOB: {job}
    CV: {cv_text}
    """
    try:
        res = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except: return None

# --- INTERFACE ---
st.title("🕵️‍♂️ AI Recruiter Dashboard")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Le Poste")
    job_desc = st.text_area("Description du besoin", height=200)

with col2:
    st.subheader("2. Les Candidats")
    files = st.file_uploader("Upload CVs", type=['pdf'], accept_multiple_files=True)
    
    if st.button("🚀 Lancer l'analyse") and files and job_desc:
        for f in files:
            txt = extract_text_from_pdf(f)
            data = analyze_candidate(job_desc, txt)
            
            if data:
                # Sauvegarde
                save_to_google_sheet(data)
                
                # Affichage
                score = data['analyse']['score_global']
                color = "green" if score > 75 else "red"
                with st.expander(f"{data['infos']['nom']} - {score}%"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Verdict:** {data['analyse']['verdict']}")
                        st.write(f"**Tel:** {data['infos']['tel']}")
                    with c2:
                        # Graphique Radar
                        r = data['radar']
                        fig = go.Figure(data=go.Scatterpolar(r=list(r.values()), theta=list(r.keys()), fill='toself'))
                        fig.update_layout(height=200, margin=dict(t=20, b=20))

                        st.plotly_chart(fig, use_container_width=True)
