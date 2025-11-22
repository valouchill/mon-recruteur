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
        v = int(float(value))
    except Exception:
        v = default
    if vmin is not None:
        v = max(vmin, v)
    if vmax is not None:
        v = min(vmax, v)
    return v


def _strip_code_fences(text: str) -> str:
    """Supprime les ```json ... ``` éventuels autour de la réponse."""
    if not text:
        return ""
    # Cherche un bloc ```...```
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return text.strip()


def _extract_json_substring(text: str) -> str:
    """
    Essaye d'extraire la partie JSON d'un texte en prenant
    du premier '{' au dernier '}'.
    """
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def normalize_analysis(raw: dict) -> dict:
    """Normalise et sécurise la structure d'analyse (typage, valeurs par défaut)."""
    if not isinstance(raw, dict):
        raw = {}

    infos_raw = raw.get("infos", {}) if isinstance(raw.get("infos"), dict) else {}
    scores_raw = raw.get("scores", {}) if isinstance(raw.get("scores"), dict) else {}
    salaire_raw = raw.get("salaire", {}) if isinstance(raw.get("salaire"), dict) else {}
    comp_raw = raw.get("competences", {}) if isinstance(raw.get("competences"), dict) else {}
    analyse_raw = raw.get("analyse", {}) if isinstance(raw.get("analyse"), dict) else {}

    data = {}

    data["infos"] = {
        "nom": str(infos_raw.get("nom", DEFAULT_ANALYSIS["infos"]["nom"])),
        "email": str(infos_raw.get("email", DEFAULT_ANALYSIS["infos"]["email"])),
        "tel": str(infos_raw.get("tel", DEFAULT_ANALYSIS["infos"]["tel"])),
        "ville": str(infos_raw.get("ville", DEFAULT_ANALYSIS["infos"]["ville"])),
        "linkedin": str(infos_raw.get("linkedin", DEFAULT_ANALYSIS["infos"]["linkedin"])),
        "experience": str(infos_raw.get("experience", DEFAULT_ANALYSIS["infos"]["experience"])),
    }

    data["scores"] = {
        "global": _to_int(scores_raw.get("global", 0), 0, 0, 100),
        "tech": _to_int(scores_raw.get("tech", 0), 0, 0, 100),
        "experience": _to_int(scores_raw.get("experience", 0), 0, 0, 100),
        "soft": _to_int(scores_raw.get("soft", 0), 0, 0, 100),
        "culture": _to_int(scores_raw.get("culture", 0), 0, 0, 100),
    }

    data["salaire"] = {
        "min": _to_int(salaire_raw.get("min", 0), 0),
        "max": _to_int(salaire_raw.get("max", 0), 0),
        "justif": str(salaire_raw.get("justif", "")),
    }

    data["historique"] = raw.get("historique", []) or []

    data["competences"] = {
        "expert": comp_raw.get("expert", []) or [],
        "intermediaire": comp_raw.get("intermediaire", []) or [],
        "manquant": comp_raw.get("manquant", []) or [],
    }

    data["analyse"] = {
        "verdict": str(analyse_raw.get("verdict", DEFAULT_ANALYSIS["analyse"]["verdict"]))
    }

    data["forces"] = raw.get("forces", []) or []
    data["risques"] = raw.get("risques", []) or []
    data["questions"] = raw.get("questions", []) or []

    return data


def safe_json_parse(response_text: str) -> dict:
    """Parse JSON de manière robuste + normalisation."""
    if not response_text:
        return DEFAULT_ANALYSIS.copy()

    # Nettoyage de base (fences markdown, texte hors JSON…)
    cleaned = _strip_code_fences(response_text)
    cleaned = _extract_json_substring(cleaned)

    # Première tentative directe
    try:
        parsed = json.loads(cleaned)
        return normalize_analysis(parsed)
    except Exception:
        pass

    # Tentative plus permissive : remplace les guillemets simples par doubles
    try:
        approx = cleaned.replace("'", '"')
        parsed = json.loads(approx)
        return normalize_analysis(parsed)
    except Exception:
        # Échec complet : renvoie un squelette par défaut pour éviter le crash
        return DEFAULT_ANALYSIS.copy()


# --- CLIENT IA ROBUSTE ---
@st.cache_resource
def get_ai_client():
    api_key = st.secrets.get("GROQ_API_KEY")
    if not api_key:
        st.error("⚠️ Clé GROQ_API_KEY manquante dans st.secrets.")
        return None
    try:
        return openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
    except Exception as e:
        st.error(f"⚠️ Erreur d'initialisation du client IA : {e}")
        return None


def save_to_sheets(data, job_desc):
    """Enregistre en base Google Sheets, sans faire planter l'app en cas d'erreur."""
    try:
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
    except Exception:
        # On ignore silencieusement pour ne pas casser l'expérience
        pass


@st.cache_data
def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        texts = []
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                texts.append(txt)
        return "\n\n".join(texts)
    except Exception:
        return ""


# --- ANALYSE IA ROBUSTE ---
@st.cache_data(ttl=1800)
def analyze_cv(job_desc: str, cv_text: str, criteria: str = ""):
    client = get_ai_client()
    if not client:
        return None

    system_msg = (
        "Tu es un ATS (outil de sélection de CV) expert en recrutement tech en France. "
        "Tu évalues la pertinence des profils par rapport à une offre donnée. "
        "IMPORTANT : tu dois répondre UNIQUEMENT avec un JSON valide, sans aucun autre texte."
    )

    prompt = f"""ANALYSE RECRUTEMENT TECHNIQUE

Contexte :
- Tu lis d'abord l'offre d'emploi.
- Tu lis ensuite le CV.
- Tu appliques les critères prioritaires fournis.
- Tu notes le candidat de façon cohérente (0 à 100).

RÈGLES DE SORTIE :
- Réponds UNIQUEMENT avec un objet JSON valide.
- AUCUN texte avant ou après le JSON.
- Utilise uniquement des guillemets doubles (") pour les clés et les chaînes.
- Pas de commentaires, pas de trailing commas.
- Tous les scores sont des entiers entre 0 et 100.
- Les salaires sont en K€ bruts annuels.

OFFRE (tronquée) :
{job_desc[:2000]}

CRITÈRES PRIORITAIRES :
{criteria}

CV (tronqué) :
{cv_text[:4000]}

FORMAT EXACT ATTENDU :

{{
  "infos": {{
    "nom": "NOM COMPLET",
    "email": "email@exemple.com",
    "tel": "01.xx.xx.xx.xx",
    "ville": "Ville",
    "linkedin": "https://linkedin.com/in/...",
    "experience": "X ans"
  }},
  "scores": {{
    "global": 85,
    "tech": 80,
    "experience": 75,
    "soft": 70,
    "culture": 65
  }},
  "salaire": {{
    "min": 45,
    "max": 55,
    "justif": "Senior Python à Paris, marché 2025"
  }},
  "historique": [
    {{
      "titre": "Dev Senior",
      "entreprise": "Société",
      "duree": "2022-Aujourd'hui",
      "mission": "Brève description des missions principales"
    }}
  ],
  "competences": {{
    "expert": ["Python", "AWS"],
    "intermediaire": ["Docker"],
    "manquant": ["Kubernetes"]
  }},
  "analyse": {{
    "verdict": "Résumé clair (1 à 3 phrases) sur l'adéquation du profil"
  }},
  "forces": [
    "5 ans d'expérience Python",
    "Projets en prod sur AWS"
  ],
  "risques": [
    "Pas d'expérience Kubernetes récente"
  ],
  "questions": [
    {{
      "type": "tech",
      "question": "Explique un déploiement complet sur AWS",
      "attendu": "Détails ELB, ASG, RDS, VPC..."
    }}
  ]
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        return safe_json_parse(content)
    except Exception as e:
        st.error(f"⚠️ Erreur durant l'appel IA : {e}")
        return None


# --- ÉTAT SESSION ---
if 'results' not in st.session_state:
    st.session_state.results = []
if 'analyze' not in st.session_state:
    st.session_state.analyze = False

st.title("👔 AI Recruiter PRO - V8.2 ✅")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📋 Configuration")

    # Offre d'emploi
    ao_pdf = st.file_uploader("📄 Offre d'emploi (PDF)", type='pdf')
    ao_text = st.text_area("Ou texte AO", height=120, placeholder="Collez l'offre...")
    job_offer = extract_pdf_text(ao_pdf.getvalue()) if ao_pdf else ao_text

    st.divider()

    # Critères
    criteria = st.text_area(
        "⚖️ Critères prioritaires",
        height=80,
        placeholder="Ex: Python obligatoire, 3+ ans exp, IDF..."
    )

    # Upload CVs
    cvs = st.file_uploader("📋 CVs (PDFs)", type='pdf', accept_multiple_files=True)

    st.divider()

    # Boutons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Analyser", type="primary"):
            if not job_offer:
                st.warning("⚠️ Merci d'ajouter une offre d'emploi (PDF ou texte).")
            elif not cvs:
                st.warning("⚠️ Merci d'ajouter au moins un CV.")
            else:
                st.session_state.analyze = True
    with col2:
        if st.button("🗑️ Reset"):
            st.session_state.results = []
            st.session_state.analyze = False
            st.rerun()

    # Stats sidebar
    if st.session_state.results:
        df_stats = pd.DataFrame(st.session_state.results)
        st.metric("Candidats", len(df_stats))
        st.metric("Meilleur score", f"{df_stats['score'].max()}%")


# --- LOGIQUE ANALYSE ---
if st.session_state.get('analyze', False) and job_offer and cvs:
    st.session_state.analyze = False
    with st.spinner(f'Analyse de {len(cvs)} CV(s)...'):
        results = []
        progress = st.progress(0)

        for i, cv_file in enumerate(cvs):
            cv_text = extract_pdf_text(cv_file.getvalue())
            if not cv_text:
                progress.progress((i + 1) / len(cvs))
                continue

            analysis = analyze_cv(job_offer, cv_text, criteria)
            if analysis:
                # Sauvegarde Sheets (best-effort)
                save_to_sheets(analysis, job_offer)

                info = analysis.get('infos', {})
                score_data = analysis.get('scores', {'global': 0})
                salaire_data = analysis.get('salaire', {})

                global_score = _to_int(score_data.get('global', 0), 0, 0, 100)

                results.append({
                    'nom': info.get('nom', 'N/A'),
                    'score': global_score,
                    'email': info.get('email', 'N/A'),
                    'linkedin': info.get('linkedin', None),
                    'salaire': f"{salaire_data.get('min', 0)}-{salaire_data.get('max', 0)}k€",
                    'data': analysis
                })

            progress.progress((i + 1) / len(cvs))

        st.session_state.results = results
        st.rerun()

# --- AFFICHAGE RÉSULTATS ---
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    df = df.sort_values('score', ascending=False)

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_score = st.slider("Score min", 0, 100, 50)
    with col_f2:
        status_filter = st.selectbox("Statut", ["Tous", "Top 3", "≥75%", "50-74%", "<50%"])

    # Application filtres
    df_filtered = df[df['score'] >= min_score].copy()

    if status_filter == "Top 3":
        df_filtered = df_filtered.head(3)
    elif status_filter == "≥75%":
        df_filtered = df_filtered[df_filtered['score'] >= 75]
    elif status_filter == "50-74%":
        df_filtered = df_filtered[(df_filtered['score'] >= 50) & (df_filtered['score'] <= 74)]
    elif status_filter == "<50%":
        df_filtered = df_filtered[df_filtered['score'] < 50]

    # Export
    csv_data = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export CSV", csv_data, "recrutement.csv", "text/csv")

    st.subheader("📊 Tableau de Bord")
    st.dataframe(
        df_filtered.drop('data', axis=1, errors='ignore'),
        use_container_width=True,
        hide_index=True,
        column_config={
            "linkedin": st.column_config.LinkColumn("LinkedIn"),
            "score": st.column_config.ProgressColumn("Score", "%d%%"),
        }
    )

    # Fiches candidats
    st.subheader("👥 Dossiers Détaillés")
    for idx, candidate in df_filtered.iterrows():
        data = candidate['data']
        score = candidate['score']

        status_class = "status-green" if score >= 75 else "status-orange" if score >= 50 else "status-red"

        with st.expander(f"👤 {candidate['nom']} • {score}% • {candidate['salaire']}", expanded=False):
            info = data.get('infos', {})
            col1, col2, col3 = st.columns([1, 1, 1])

            with col1:
                st.markdown(f"**📧** {info.get('email', 'N/A')}")
            with col2:
                st.markdown(f"**📍** {info.get('ville', 'N/A')}")
            with col3:
                st.markdown(f"**🔗** {info.get('linkedin', 'N/A')}")

            main_col, side_col = st.columns([3, 2])

            with main_col:
                st.markdown("### 🎯 Analyse")
                st.success(data.get('analyse', {}).get('verdict', 'Analyse non disponible'))

                forces = data.get('forces', [])
                risques = data.get('risques', [])

                c_f, c_r = st.columns(2)
                with c_f:
                    st.markdown("**✅ Forces**")
                    if forces:
                        for force in forces[:5]:
                            st.markdown(f"• {force}")
                    else:
                        st.caption("Aucune force identifiée.")
                with c_r:
                    st.markdown("**⚠️ Risques**")
                    if risques:
                        for risque in risques[:5]:
                            st.error(f"• {risque}")
                    else:
                        st.caption("Pas de risques majeurs identifiés.")

                hist = data.get('historique', [])
                if hist:
                    st.markdown("### 📈 Parcours Pro")
                    for poste in hist[:3]:
                        st.markdown(f"**{poste.get('titre', '')}** chez _{poste.get('entreprise', '')}_")
                        st.caption(poste.get('duree', ''))
                        st.caption(poste.get('mission', ''))

            with side_col:
                scores = data.get('scores', {})
                fig = go.Figure(data=go.Scatterpolar(
                    r=[
                        scores.get('tech', 0),
                        scores.get('experience', 0),
                        scores.get('soft', 0),
                        scores.get('culture', 0)
                    ],
                    theta=['Tech', 'Exp', 'Soft', 'Fit'],
                    fill='toself'
                ))
                fig.update_layout(
                    height=250,
                    margin=dict(l=20, r=20, t=20, b=20),
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100]))
                )
                st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}")

                skills = data.get('competences', {})
                st.markdown("### 🛠️ Skills")

                expert = skills.get('expert', [])
                intermediaire = skills.get('intermediaire', [])
                missing = skills.get('manquant', [])

                if expert:
                    st.markdown("**🏆 Expert**")
                    for skill in expert:
                        st.markdown(f"✅ {skill}")

                if intermediaire:
                    st.markdown("**🧩 Intermédiaire**")
                    for skill in intermediaire:
                        st.markdown(f"• {skill}")

                if missing:
                    st.markdown("**❌ Manque**")
                    for skill in missing:
                        st.markdown(f"❌ {skill}")

else:
    st.info("👈 **Chargez l'offre + CVs** pour lancer l'analyse")
    st.balloons()
