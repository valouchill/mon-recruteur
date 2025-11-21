import streamlit as st

st.set_page_config(page_title="Debug Secrets")
st.title("🕵️‍♂️ Espion des Secrets")

st.write("Voici la structure exacte que Streamlit détecte :")

# 1. AFFICHER TOUTES LES CLÉS PRINCIPALES
keys = list(st.secrets.keys())
st.write(f"🔑 Clés principales trouvées : `{keys}`")

# 2. TEST SPÉCIFIQUE GROQ
if "GROQ_API_KEY" in st.secrets:
    valeur = st.secrets["GROQ_API_KEY"]
    st.success(f"✅ GROQ_API_KEY est bien là ! (Début : {valeur[:4]}...)")
else:
    st.error("❌ GROQ_API_KEY est INTROUVABLE à la racine.")

# 3. TEST SI GROQ EST CACHÉ DANS GOOGLE (Erreur fréquente)
if "gcp_service_account" in st.secrets:
    gcp = st.secrets["gcp_service_account"]
    st.info("📂 Le dossier 'gcp_service_account' existe.")
    
    # Est-ce que la clé Groq est tombée dedans par erreur ?
    if "GROQ_API_KEY" in gcp:
        st.error("⚠️ ALERTE : Votre clé GROQ est coincée À L'INTÉRIEUR du bloc Google !")
        st.warning("👉 Solution : Déplacez la ligne `GROQ_API_KEY = ...` tout en haut du fichier Secrets.")
    
    # Vérification du contenu Google
    if "private_key" in gcp:
        st.success("✅ Clé privée Google présente.")
    else:
        st.error("❌ Clé privée Google manquante dans le bloc.")
else:
    st.warning("⚠️ Le bloc 'gcp_service_account' est absent.")
