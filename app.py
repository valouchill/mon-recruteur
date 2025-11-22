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
st.set_page_config(page_title="AI Recruiter PRO - V8.2", layout="wide", page_icon="👔")

# CSS optimisé
st.markdown("""
<style>
.metric-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; text-align: center; }
.st-expanderHeader { font-weight: 600 !important; }
.status-green { background: #d4edda; color: #155724; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
.status-orange { background: #fff3cd; color: #856404; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
.status-red { background: #f8d7da; color: #721c24; padding: 5px 12px; border-radius: 20px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ---------- CONSTANTES & HELPERS ----------

DEFAULT_ANALYSIS = {
    "infos": {
        "nom": "N/A",
        "email": "N/A",
        "tel": "",
        "ville": "",
        "linkedin": "",
        "experience": ""
    },
    "scores": {
        "global": 0,
        "tech": 0,
        "experience": 0,
        "soft": 0,
        "culture": 0
    },
    "salaire": {
        "min": 0,
        "max": 0,
        "justif": ""
    },
    "historique": [],
    "competences": {
        "expert": [],
        "intermediaire": [],
        "manquant": []
    },
    "analyse": {
        "verdict": "Analyse non disponible"
    },
    "forces": [],
    "risques": [],
    "questions": []
}


def _to_int(value, default=0, vmin=None, vmax=None):
    """Convertit en int avec limites optionnelles."""
    try:
        # Nettoyage basique (ex: "45k" -> 45)
        if isinstance(value, str):
            value = re.sub(r"[^\d\.]", "", value)
        v = int(float(value))
    except Exception:
        v = default
    if vmin is not None:
        v = max(vmin, v)
    if vmax is not None:
        v = min(vmax, v)
    return v


def _strip_code_fences(text: str) -> str:
    """Supprime les `````` éventuels autour de la réponse."""
    if not text:
        return ""
    fence_match = re.search(r"``````", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return text.strip()


def _extract_json_substring(text: str) -> str:
    """Extrait la partie JSON entre le premier { et le dernier }."""
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def normalize_analysis(raw: dict) -> dict:
    """Normalise et sécurise la structure d'analyse."""
    if not isinstance(raw, dict):
        raw = {}

    infos_raw = raw.get("infos", {}) if isinstance(raw.get("infos"), dict) else {}
    scores_raw = raw.get("scores", {}) if isinstance(raw.get("scores"), dict) else {}
    salaire_raw = raw.get("salaire", {}) if isinstance(raw.get("salaire"), dict) else {}
    comp_raw = raw.get("competences", {}) if isinstance(raw.get("competences"), dict) else {}
    analyse_raw = raw.get("analyse", {}) if isinstance(raw.get("analyse"), dict) else {}

    data = {}
    
    # Infos
    data["infos"] = {
        "nom": str(infos_raw.get("nom", "N/A")),
        "email": str(infos_raw.get("email", "N/A")),
        "tel": str(infos_raw.get("tel", "")),
        "ville": str(infos_raw.get("ville", "")),
        "linkedin": str(infos_raw.get("linkedin", "")),
        "experience": str(infos_raw.get("experience", "")),
    }

    # Scores (Force 0-100)
    data["scores"] = {
        "global": _to_int(scores_raw.get("global", 0), 0, 0, 100),
        "tech": _to_int(scores_raw.get("tech", 0), 0, 0, 100),
        "experience": _to_int(scores_raw.get("experience", 0), 0, 0, 100),
        "soft": _to_int(scores_raw.get("soft", 0), 0, 0, 100),
        "culture": _to_int(scores_raw.get("culture", 0), 0, 0, 100),
    }

    # Salaire
    data["salaire"] = {
        "min": _to_int(salaire_raw.get("min", 0), 0),
        "max": _to_int(salaire_raw.get("max", 0), 0),
        "justif": str(salaire_raw.get("justif", "")),
    }

    # Listes simples
    data["historique"] = raw.get("historique", []) if isinstance(raw.get("historique"), list) else []
    data["forces"] = raw.get("forces", []) if isinstance(raw.get("forces"), list) else []
    data["risques"] = raw.get("risques", []) if isinstance(raw.get("risques"), list) else []
    data["questions"] = raw.get("questions", []) if isinstance(raw.get("questions"), list) else []

    # Compétences
    data["competences"] = {
        "expert": comp_raw.get("expert", []) if isinstance(comp_raw.get("expert"), list) else [],
        "intermediaire": comp_raw.get("intermediaire", []) if isinstance(comp_raw.get("intermediaire"), list) else [],
        "manquant": comp_raw.get("manquant", []) if isinstance(comp_raw.get("manquant"), list) else [],
    }

    data["analyse"] = {
        "verdict": str(analyse_raw.get("verdict", "Analyse non disponible"))
    }

    return data


def safe_json_parse(response_text: str) -> dict:
    """Parse JSON robuste."""
    if not response_text:
        return DEFAULT_ANALYSIS.copy()

    cleaned = _strip_code_fences(response_text)
    cleaned = _extract_json_substring(cleaned)

    try:
        parsed = json.loads(cleaned)
        return normalize_analysis(parsed)
    except Exception:
        # Retry loose (guillemets simples)
        try:
            approx = cleaned.replace("'", '"')
            parsed = json.loads(approx)
            return normalize_analysis(parsed)
        except:
            return DEFAULT_ANALYSIS.copy()


# --- CLIENT IA ---
@st.cache_resource
def get_ai_client():
    try:
        # Vérifie les deux noms de clés possibles pour la compatibilité
        api_key = st.secrets.get("GROQ_API_KEY")
        if not api_key:
            return None
        return openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
    except Exception:
        return None


def save_to_sheets(data, job_desc):
    try:
        if "gcp_service_account" in st.secrets:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                dict(st.secrets["gcp_service_account"]), scope
            )
            client = gspread.authorize(creds)
            sheet = client.open("Recrutement_DB").sheet1
            infos, scores = data.get('infos', {}), data.get('scores', {})
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                infos.get('nom'),
                f"{scores.get('global')}%",
                infos.get('email'),
                infos.get('linkedin', ''),
                job_desc[:50]
            ])
    except:
        pass


@st.cache_data
def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except:
        return ""


# --- ANALYSE IA ---
@st.cache_data(ttl=1800)
def analyze_cv(job_desc: str, cv_text: str, criteria: str = ""):
    client = get_ai_client()
    if not client:
        return None

    prompt = f"""ANALYSE RECRUTEMENT TECHNIQUE

CONTEXTE:
Tu es un Expert Recrutement Tech. Tu dois analyser ce CV pour cette Offre.

OFFRE:
{job_desc[:2000]}

CRITÈRES PRIORITAIRES:
{criteria}

CV:
{cv_text[:4000]}

FORMAT DE SORTIE (JSON STRICT UNIQUEMENT, PAS DE TEXTE):
{{
  "infos": {{ "nom": "Nom Complet", "email": "email", "tel": "tel", "ville": "ville", "linkedin": "url", "experience": "X ans" }},
  "scores": {{ "global": 0-100, "tech": 0-100, "experience": 0-100, "soft": 0-100, "culture": 0-100 }},
  "salaire": {{ "min": 45, "max": 55, "justif": "Justification courte" }},
  "historique": [ {{ "titre": "Poste", "entreprise": "Boite", "duree": "Dates", "mission": "Résumé" }} ],
  "competences": {{ "expert": ["Skill A"], "intermediaire": ["Skill B"], "manquant": ["Skill C"] }},
  "analyse": {{ "verdict": "Synthèse du profil en 2 phrases" }},
  "forces": ["Point fort 1", "Point fort 2"],
  "risques": ["Risque 1"],
  "questions": [ {{ "type": "tech", "question": "Question ?", "attendu": "Réponse attendue" }} ]
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=2500,
        )
        return safe_json_parse(response.choices[0].message.content)
    except:
        return None


# --- ÉTAT SESSION ---
if 'results' not in st.session_state:
    st.session_state.results = []
if 'analyze' not in st.session_state:
    st.session_state.analyze = False

# --- UI ---
st.title("👔 AI Recruiter PRO - V8.2 ✅")

with st.sidebar:
    st.header("📋 Configuration")
    
    # AO
    ao_pdf = st.file_uploader("📄 Offre d'emploi (PDF)", type='pdf')
    ao_text = st.text_area("Ou texte AO", height=100, placeholder="Collez l'offre ici...")
    job_offer = extract_pdf_text(ao_pdf.getvalue()) if ao_pdf else ao_text
    
    st.divider()
    criteria = st.text_area("⚖️ Critères", height=80, placeholder="Ex: Python, Senior...")
    cvs = st.file_uploader("📋 CVs (PDFs)", type='pdf', accept_multiple_files=True)
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Analyser", type="primary"):
            st.session_state.analyze = True
    with col2:
        if st.button("🗑️ Reset"):
            st.session_state.results = []
            st.session_state.analyze = False
            st.rerun()
            
    if st.session_state.results:
        df_stats = pd.DataFrame(st.session_state.results)
        st.metric("Candidats", len(df_stats))
        st.metric("Top Score", f"{df_stats['score'].max()}%")


# --- LOGIQUE ---
if st.session_state.analyze and job_offer and cvs:
    st.session_state.analyze = False
    if not get_ai_client():
        st.error("❌ Clé API manquante (.streamlit/secrets.toml)")
    else:
        with st.spinner(f"Analyse de {len(cvs)} profils..."):
            results = []
            bar = st.progress(0)
            for i, file in enumerate(cvs):
                txt = extract_pdf_text(file.getvalue())
                if txt:
                    data = analyze_cv(job_offer, txt, criteria)
                    if data:
                        save_to_sheets(data, job_offer)
                        results.append({
                            'nom': data['infos']['nom'],
                            'score': data['scores']['global'],
                            'data': data
                        })
                bar.progress((i+1)/len(cvs))
            st.session_state.results = results
            st.rerun()

# --- RÉSULTATS ---
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results).sort_values('score', ascending=False)
    
    # Filtres
    c1, c2 = st.columns(2)
    with c1: min_s = st.slider("Score Min", 0, 100, 50)
    with c2: stat = st.selectbox("Filtre Rapide", ["Tous", "Top 3", ">75%"])
    
    df_show = df[df['score'] >= min_s].copy()
    if stat == "Top 3": df_show = df_show.head(3)
    elif stat == ">75%": df_show = df_show[df_show['score'] >= 75]
    
    # Export
    csv = df_show.to_csv(index=False).encode('utf-8')
    st.download_button("📥 CSV", csv, "export.csv", "text/csv")
    
    # Tableau
    st.subheader("📊 Synthèse")
    st.dataframe(
        df_show.drop(columns=['data']), 
        use_container_width=True, 
        hide_index=True,
        column_config={"score": st.column_config.ProgressColumn("Match", format="%d%%")}
    )
    
    # Détail
    st.subheader("📂 Dossiers")
    for idx, row in df_show.iterrows():
        d = row['data']
        score = row['score']
        info = d['infos']
        
        with st.expander(f"👤 {info['nom']} • {score}% • {d['salaire']['min']}-{d['salaire']['max']}k€", expanded=False):
            
            # Header Contact
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"📧 **{info['email']}**")
            c2.markdown(f"📍 **{info['ville']}**")
            lnk = info['linkedin']
            c3.markdown(f"🔗 **[{'LinkedIn' if lnk else 'N/A'}]({lnk})**" if lnk else "🔗 **N/A**")
            
            # Corps
            main, side = st.columns([2, 1])
            
            with main:
                st.success(f"💡 {d['analyse']['verdict']}")
                
                # Forces / Risques
                cf, cr = st.columns(2)
                with cf:
                    st.markdown("**✅ Forces**")
                    for f in d['forces'][:4]: st.markdown(f"- {f}")
                with cr:
                    st.markdown("**⚠️ Risques**")
                    for r in d['risques'][:4]: st.markdown(f"- {r}")
                
                # Historique
                if d['historique']:
                    st.markdown("---")
                    st.markdown("**📅 Parcours**")
                    for h in d['historique'][:3]:
                        st.markdown(f"**{h.get('titre','')}** @ {h.get('entreprise','')}")
                        st.caption(f"{h.get('duree','')} | {h.get('mission','')}")

            with side:
                # Radar
                sc = d['scores']
                fig = go.Figure(data=go.Scatterpolar(
                    r=[sc['tech'], sc['experience'], sc['soft'], sc['culture']],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself'
                ))
                fig.update_layout(height=200, margin=dict(t=20, b=20, l=20, r=20), polar=dict(radialaxis=dict(range=[0, 100])))
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")
                
                # Skills
                st.markdown("**🏆 Expert**")
                for s in d['competences']['expert']: st.markdown(f"`{s}`")
                
                st.markdown("**🧩 Intermédiaire**")
                for s in d['competences']['intermediaire']: st.markdown(f"`{s}`")
                
                st.markdown("**❌ Manquant**")
                for s in d['competences']['manquant']: st.markdown(f"~~{s}~~")

else:
    st.info("👈 Chargez une offre et des CVs pour démarrer.")
