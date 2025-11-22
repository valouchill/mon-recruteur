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
import re
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="AI Recruiter PRO - V10 Precision", layout="wide", page_icon="🎯")

st.markdown("""
<style>
    .score-badge { font-size: 1.5rem; font-weight: bold; padding: 10px 20px; border-radius: 10px; text-align: center; color: white; }
    .score-high { background: #10b981; box-shadow: 0 4px 10px rgba(16, 185, 129, 0.3); }
    .score-mid { background: #f59e0b; box-shadow: 0 4px 10px rgba(245, 158, 11, 0.3); }
    .score-low { background: #ef4444; box-shadow: 0 4px 10px rgba(239, 68, 68, 0.3); }
    
    .salary-box { border: 2px solid #e5e7eb; border-radius: 8px; padding: 15px; text-align: center; background: #f9fafb; }
    .salary-val { font-size: 1.4rem; font-weight: 800; color: #1f2937; }
    .salary-sub { font-size: 0.9rem; color: #6b7280; }
    
    .skill-tag { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin: 3px; }
    .tag-match { background: #d1fae5; color: #065f46; border: 1px solid #34d399; }
    .tag-miss { background: #fee2e2; color: #991b1b; border: 1px solid #f87171; text-decoration: line-through; }
</style>
""", unsafe_allow_html=True)

# --- 1. INTELLIGENCE & PARSING ---

DEFAULT_DATA = {
    "infos": {"nom": "Inconnu", "email": "", "tel": "", "ville": "", "linkedin": "", "poste_actuel": ""},
    "scores": {"global": 0, "tech": 0, "experience": 0, "soft": 0, "fit": 0},
    "salaire": {"min": 0, "max": 0, "confiance": "Faible", "analyse": "Données insuffisantes"},
    "analyse": {"verdict": "N/A", "points_forts": [], "points_faibles": []},
    "competences": {"match": [], "manquant": []},
    "historique": [],
    "entretien": []
}

def normalize_json(raw):
    """Nettoie et structure les données pour éviter tout crash."""
    if not isinstance(raw, dict): raw = {}
    
    data = DEFAULT_DATA.copy()
    
    # Infos
    ri = raw.get('infos', {})
    data['infos'] = {
        "nom": str(ri.get('nom', 'Inconnu')),
        "email": str(ri.get('email', 'N/A')),
        "tel": str(ri.get('tel', 'N/A')),
        "ville": str(ri.get('ville', 'Non précisé')),
        "linkedin": str(ri.get('linkedin', '')),
        "poste_actuel": str(ri.get('poste_actuel', 'Candidat'))
    }
    
    # Scores (Conversion int forcée)
    rs = raw.get('scores', {})
    data['scores'] = {
        "global": int(rs.get('global', 0)),
        "tech": int(rs.get('tech', 0)),
        "experience": int(rs.get('experience', 0)),
        "soft": int(rs.get('soft', 0)),
        "fit": int(rs.get('fit', 0))
    }
    
    # Salaire
    rsa = raw.get('salaire', {})
    data['salaire'] = {
        "min": int(rsa.get('min', 0)),
        "max": int(rsa.get('max', 0)),
        "confiance": str(rsa.get('confiance', 'Moyenne')),
        "analyse": str(rsa.get('analyse', ''))
    }
    
    # Listes
    data['competences']['match'] = raw.get('competences', {}).get('match', [])
    data['competences']['manquant'] = raw.get('competences', {}).get('manquant', [])
    data['analyse']['points_forts'] = raw.get('analyse', {}).get('points_forts', [])
    data['analyse']['points_faibles'] = raw.get('analyse', {}).get('points_faibles', [])
    data['analyse']['verdict'] = raw.get('analyse', {}).get('verdict', 'N/A')
    data['historique'] = raw.get('historique', [])
    data['entretien'] = raw.get('entretien', [])
    
    return data

# --- 2. IA CLIENT ---
@st.cache_resource
def get_client():
    try:
        return openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])
    except: return None

def extract_pdf(file):
    try:
        return "\n".join([p.extract_text() for p in PdfReader(io.BytesIO(file)).pages if p.extract_text()])
    except: return ""

# --- 3. PROMPT DE SCORING AVANCÉ ---
@st.cache_data(ttl=3600)
def analyze_candidate(job, cv, criteria=""):
    client = get_client()
    if not client: return None
    
    # Matrice de salaire injectée dans le contexte
    salary_context = """
    RÉFÉRENTIEL SALAIRE FRANCE 2024/2025 (Tech/Digital) :
    - Junior (0-2 ans): 35k-45k (Province) | 40k-50k (Paris)
    - Confirmé (3-5 ans): 45k-55k (Province) | 50k-65k (Paris)
    - Senior (5-8 ans): 55k-70k (Province) | 65k-85k (Paris)
    - Lead/Expert (8+ ans): 70k+ (Province) | 80k-120k (Paris)
    AJUSTEMENT : Si le candidat est en Ile-de-France, vise la fourchette haute. Sinon, fourchette basse.
    """
    
    prompt = f"""
    Tu es un Expert Recrutement. Analyse ce profil avec une rigueur mathématique.
    
    INPUTS:
    - OFFRE: {job[:2000]}
    - CRITÈRES: {criteria}
    - CV: {cv[:3500]}
    - CONTEXTE SALAIRE: {salary_context}
    
    TACHE 1 : CALCUL DU SCORE (Ne sois pas complaisant)
    - Tech (40%): Les langages/outils clés sont-ils là ?
    - Expérience (30%): La durée et le secteur correspondent-ils ?
    - Soft/Fit (30%): Le ton et le parcours collent-ils ?
    
    TACHE 2 : SALAIRE
    - Estime la fourchette selon l'expérience réelle et la ville du candidat.
    
    FORMAT DE SORTIE (JSON STRICT):
    {{
        "infos": {{ "nom": "Nom Prénom", "email": "...", "tel": "...", "ville": "Ville détectée", "linkedin": "...", "poste_actuel": "..." }},
        "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "fit": 0-100 }},
        "salaire": {{ 
            "min": int (k€), "max": int (k€), 
            "confiance": "Haute/Moyenne/Faible", 
            "analyse": "Ex: Profil Senior Parisien, prix marché élevé." 
        }},
        "competences": {{ "match": ["Skill A", "Skill B"], "manquant": ["Skill C"] }},
        "analyse": {{ 
            "verdict": "Synthèse 2 lignes.", 
            "points_forts": ["Force 1", "Force 2"], 
            "points_faibles": ["Faible 1", "Faible 2"] 
        }},
        "historique": [ {{ "titre": "...", "entreprise": "...", "duree": "...", "mission": "..." }} ],
        "entretien": [ {{ "theme": "Tech", "question": "...", "attendu": "..." }} ]
    }}
    """
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0  # Température 0 pour un résultat analytique stable
        )
        raw_json = json.loads(res.choices[0].message.content)
        return normalize_json(raw_json)
    except: return None

# --- 4. INTERFACE ---
if 'results' not in st.session_state: st.session_state.results = []

st.title("🎯 AI Recruiter PRO - Precision Engine")

with st.sidebar:
    st.header("Configuration")
    ao_file = st.file_uploader("Offre (PDF)", type='pdf')
    ao_txt = st.text_area("Ou texte Offre", height=100)
    job_text = extract_pdf(ao_file.getvalue()) if ao_file else ao_txt
    
    criteria = st.text_area("Critères Clés (Pondération)", height=80, placeholder="Ex: Anglais obligatoire, Python Expert...")
    
    st.divider()
    cv_files = st.file_uploader("Candidats (PDF)", type='pdf', accept_multiple_files=True)
    
    c1, c2 = st.columns(2)
    if c1.button("⚡ Analyser", type="primary"):
        if job_text and cv_files: st.session_state.analyze = True
    if c2.button("🗑️ Reset"):
        st.session_state.results = []
        st.rerun()

# LOGIQUE
if st.session_state.get('analyze', False):
    st.session_state.analyze = False
    
    results = []
    bar = st.progress(0)
    for i, f in enumerate(cv_files):
        txt = extract_pdf(f.getvalue())
        if txt:
            d = analyze_candidate(job_text, txt, criteria)
            if d: results.append(d)
        bar.progress((i+1)/len(cv_files))
    
    st.session_state.results = results
    st.rerun()

# AFFICHAGE
if st.session_state.results:
    # Trie par score
    df = pd.DataFrame([
        {'Nom': r['infos']['nom'], 'Score': r['scores']['global'], 'Poste': r['infos']['poste_actuel'], 'data': r} 
        for r in st.session_state.results
    ]).sort_values('Score', ascending=False)
    
    c_stat1, c_stat2, c_stat3 = st.columns(3)
    c_stat1.metric("Candidats", len(df))
    c_stat2.metric("Top Score", f"{df.iloc[0]['Score']}%" if not df.empty else "0%")
    c_stat3.download_button("📥 Export Excel", df.drop(columns=['data']).to_csv().encode('utf-8'), "export.csv")
    
    st.divider()

    for idx, row in df.iterrows():
        d = row['data']
        info = d['infos']
        score = d['scores']['global']
        
        # Couleur dynamique
        score_class = "score-high" if score >= 75 else "score-mid" if score >= 50 else "score-low"
        
        with st.expander(f"{info['nom']} | {score}% | {info['poste_actuel']}", expanded=True if idx==0 else False):
            
            # HEADER GRID
            c_bio, c_score, c_salary = st.columns([2, 1, 1])
            
            with c_bio:
                st.markdown(f"### 👤 {info['nom']}")
                st.caption(f"📍 {info['ville']} | 📧 {info['email']}")
                if info['linkedin']: st.markdown(f"🔗 [Profil LinkedIn]({info['linkedin']})")
                st.info(f"🧠 **Verdict :** {d['analyse']['verdict']}")
            
            with c_score:
                st.markdown(f'<div class="score-badge {score_class}">{score}%</div>', unsafe_allow_html=True)
                # Mini Radar
                fig = go.Figure(data=go.Scatterpolar(
                    r=[d['scores']['tech'], d['scores']['experience'], d['scores']['soft'], d['scores']['fit']],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself'
                ))
                fig.update_layout(height=150, margin=dict(t=20, b=20, l=20, r=20), polar=dict(radialaxis=dict(visible=False, range=[0, 100])))
                st.plotly_chart(fig, use_container_width=True, key=f"rad_{idx}")

            with c_salary:
                st.markdown('<div class="salary-box">', unsafe_allow_html=True)
                st.markdown(f'<div class="salary-val">{d["salaire"]["min"]} - {d["salaire"]["max"]} k€</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="salary-sub">Confiance: {d["salaire"]["confiance"]}</div>', unsafe_allow_html=True)
                st.caption(d["salaire"]["analyse"])
                st.markdown('</div>', unsafe_allow_html=True)

            # SKILLS & ANALYSIS
            c_skills, c_details = st.columns([1, 1])
            
            with c_skills:
                st.subheader("🛠️ Compétences")
                for s in d['competences']['match']:
                    st.markdown(f'<span class="skill-tag tag-match">✓ {s}</span>', unsafe_allow_html=True)
                for s in d['competences']['manquant']:
                    st.markdown(f'<span class="skill-tag tag-miss">✕ {s}</span>', unsafe_allow_html=True)
            
            with c_details:
                st.subheader("⚖️ Balance")
                col_f, col_r = st.columns(2)
                with col_f:
                    st.markdown("**✅ Forces**")
                    for f in d['analyse']['points_forts'][:3]: st.markdown(f"- {f}")
                with col_r:
                    st.markdown("**⚠️ Vigilance**")
                    for f in d['analyse']['points_faibles'][:3]: st.markdown(f"- {f}")

            # ENTRETIEN & HISTO
            tabs = st.tabs(["🎤 Guide Entretien", "📅 Historique"])
            with tabs[0]:
                for q in d['entretien'][:3]:
                    st.markdown(f"**Q ({q.get('theme','Général')}):** {q.get('question')}")
                    st.caption(f"💡 *Attendu:* {q.get('attendu')}")
            
            with tabs[1]:
                for h in d['historique']:
                    st.markdown(f"**{h.get('titre')}** chez *{h.get('entreprise')}* ({h.get('duree')})")
                    st.caption(h.get('mission'))

else:
    st.info("👈 Chargez une offre et des CVs pour démarrer.")
