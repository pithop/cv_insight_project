# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
from openai import OpenAI
import PyPDF2
import json
import io
import time
import traceback # Pour un meilleur débogage

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="RH+ Pro | Analyse Multi-CV",
    page_icon="🚀",
    layout="wide"
)

# --- INITIALISATION DU SESSION STATE ---
# C'est la clé ! On s'assure que les variables persistent.
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'file_contents' not in st.session_state:
    st.session_state.file_contents = {}
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# --- FONCTIONS CLÉS ---

def extract_text_from_pdf(file_object):
    """Extrait le texte d'un objet fichier PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = "".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        return text
    except Exception:
        return None

def get_single_cv_analysis(cv_text, filename, job_description_text):
    """
    Envoie UN SEUL CV à l'API pour analyse et retourne un objet JSON pour ce candidat.
    """
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=st.secrets["OPENROUTER_API_KEY"],
            timeout=180.0 
        )
        
        prompt = f"""
        En tant qu'expert en recrutement IA, votre mission est d'analyser le CV suivant par rapport à une description de poste et de renvoyer une analyse structurée en JSON.

        DESCRIPTION DU POSTE :
        ---
        {job_description_text}
        ---

        CV DU CANDIDAT (nom du fichier: {filename}):
        ---
        {cv_text}
        ---

        INSTRUCTIONS STRICTES :
        1. Analysez le CV fourni.
        2. Déterminez un score de compatibilité global sur 100.
        3. Extrayez le nom complet du candidat.
        4. Rédigez un résumé très court (2 lignes max) du profil.
        5. Listez les 3 points forts principaux qui correspondent à l'offre.
        6. Renvoyez votre analyse sous la forme d'un unique objet JSON. N'ajoutez AUCUN autre texte ou "```json".

        Exemple de sortie attendue :
        {{
            "nom_fichier": "{filename}",
            "nom": "Jean Dupont",
            "score": 85,
            "resume": "Profil technique solide avec 5 ans d'expérience...",
            "points_forts": [
                "Maîtrise de Python et Django.",
                "Expérience en gestion de projet.",
                "Bonne connaissance des bases de données SQL."
            ]
        }}
        """

        response = client.chat.completions.create(
            model="google/gemma-2-9b-it:free", 
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        
        if response.choices and response.choices[0].message.content:
            raw_response = response.choices[0].message.content.strip()
            try:
                if raw_response.startswith("```json"):
                    raw_response = raw_response[7:-3].strip()
                return json.loads(raw_response)
            except json.JSONDecodeError:
                st.warning(f"L'IA a retourné un format invalide pour {filename}. Réponse :")
                st.code(raw_response)
                return None
        else:
            return None

    except Exception as e:
        st.warning(f"L'analyse de {filename} a échoué (Raison: {e}). Passage au suivant.")
        traceback.print_exc()
        return None

# --- INTERFACE UTILISATEUR (UI) ---
st.title("🚀 RH+ Pro")
st.markdown("Optimisez votre présélection. Chargez plusieurs CV, analysez-les en quelques secondes et identifiez les meilleurs talents.")
st.markdown("---")

st.subheader("1. Description du Poste")
job_description = st.text_area("Collez ici l'offre d'emploi complète", height=250, label_visibility="collapsed")

st.subheader("2. CV des Candidats")
uploaded_files = st.file_uploader(
    "Chargez un ou plusieurs CV au format PDF",
    type="pdf",
    accept_multiple_files=True,
    label_visibility="collapsed"
)

st.markdown("")
analyze_button = st.button("Analyser les Candidatures", type="primary", use_container_width=True)
st.markdown("---")

# --- LOGIQUE DE TRAITEMENT ---
if analyze_button:
    if not job_description.strip():
        st.warning("⚠️ Veuillez fournir une description de poste.")
    elif not uploaded_files:
        st.warning("⚠️ Veuillez charger au moins un CV.")
    else:
        # CORRECTION : On réinitialise le state avant une NOUVELLE analyse
        st.session_state.all_results = []
        st.session_state.file_contents = {}
        st.session_state.analysis_done = True # On indique que l'analyse a été lancée
        
        progress_bar = st.progress(0, text="Initialisation de l'analyse...")
        
        for i, uploaded_file in enumerate(uploaded_files):
            progress_text = f"Analyse de {uploaded_file.name} ({i+1}/{len(uploaded_files)})..."
            progress_bar.progress((i + 1) / len(uploaded_files), text=progress_text)
            
            file_bytes = uploaded_file.getvalue()
            # CORRECTION : On sauvegarde les bytes du fichier dans le session state
            st.session_state.file_contents[uploaded_file.name] = file_bytes
            
            text = extract_text_from_pdf(io.BytesIO(file_bytes))
            
            if text:
                single_result = get_single_cv_analysis(text, uploaded_file.name, job_description)
                if single_result:
                    # CORRECTION : On sauvegarde le résultat dans le session state
                    st.session_state.all_results.append(single_result)
            else:
                 st.warning(f"Impossible d'extraire le texte de {uploaded_file.name}. Fichier ignoré.")
        
        progress_bar.empty()

# --- AFFICHAGE DES RÉSULTATS (MAINTENANT INDÉPENDANT) ---
# Cette partie s'exécute maintenant à CHAQUE rechargement, y compris
# après un clic sur "Télécharger", car les données sont dans st.session_state.
if st.session_state.analysis_done:
    if st.session_state.all_results:
        st.subheader("🏆 Classement des Meilleurs Profils")
        
        sorted_results = sorted(st.session_state.all_results, key=lambda x: x.get('score', 0), reverse=True)
        
        for i, candidate in enumerate(sorted_results): 
            score = candidate.get('score', 0)
            badge_icon = "🥇" if score >= 85 else "🥈" if score >= 70 else "🥉"

            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"### {badge_icon} {candidate.get('nom', 'N/A')} ({candidate.get('nom_fichier', 'N/A')})")
                    st.markdown(f"**Résumé :** {candidate.get('resume', 'N/A')}")
                    st.markdown("**Points forts pour ce poste :**")
                    points_forts = candidate.get('points_forts', ['Aucun identifié.'])
                    for point in points_forts:
                        st.markdown(f"- {point}")

                with col2:
                    st.metric(label="Score", value=f"{score}%")
                    original_filename = candidate.get('nom_fichier')
                    
                    # On lit les données du fichier depuis le session state
                    if original_filename and original_filename in st.session_state.file_contents:
                        st.download_button(
                            label="📄 Télécharger le CV",
                            data=st.session_state.file_contents[original_filename],
                            file_name=original_filename,
                            mime="application/pdf",
                            key=f"btn_{original_filename}_{i}" 
                        )
    else:
        # S'affiche si l'analyse a été lancée mais a échoué pour tous les CV
        st.error("L'analyse a échoué pour tous les CV fournis. L'IA n'a pas pu retourner de classement.")