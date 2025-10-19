# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
from openai import OpenAI
import PyPDF2
import json
import io
import time # Ajout pour une meilleure gestion du spinner

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="RH+ Pro | Analyse Multi-CV",
    page_icon="🚀",
    layout="wide"
)

# --- FONCTIONS CLÉS ---

def extract_text_from_pdf(file_object):
    """Extrait le texte d'un objet fichier PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = "".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        return text
    except Exception:
        return None

# --- MODIFICATION MAJEURE : ANALYSE D'UN SEUL CV À LA FOIS ---
def get_single_cv_analysis(cv_text, filename, job_description_text):
    """
    Envoie UN SEUL CV à l'API pour analyse et retourne un objet JSON pour ce candidat.
    """
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=st.secrets["OPENROUTER_API_KEY"],
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
        6. Renvoyez votre analyse sous la forme d'un unique objet JSON. N'ajoutez AUCUN autre texte.
        7. Le JSON doit contenir les clés suivantes : "nom_fichier", "nom", "score", "resume", "points_forts".
        """

        response = client.chat.completions.create(
            model="google/gemma-2-9b-it:free",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        
        if response.choices and response.choices[0].message.content:
            # Nettoyage au cas où l'API renvoie ```json ... ```
            json_response_str = response.choices[0].message.content
            if json_response_str.startswith("```json"):
                json_response_str = json_response_str[7:-3].strip()
            return json.loads(json_response_str)
        else:
            return None

    except Exception:
        # En cas d'erreur sur un CV, on renvoie None pour ne pas bloquer les autres
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

# --- LOGIQUE DE TRAITEMENT ET AFFICHAGE DES RÉSULTATS (AMÉLIORÉE) ---
if analyze_button:
    if not job_description.strip():
        st.warning("⚠️ Veuillez fournir une description de poste.")
    elif not uploaded_files:
        st.warning("⚠️ Veuillez charger au moins un CV.")
    else:
        all_results = []
        file_contents = {}
        
        # Barre de progression pour un meilleur feedback utilisateur
        progress_bar = st.progress(0, text="Initialisation de l'analyse...")
        
        # --- NOUVELLE LOGIQUE : BOUCLE SUR CHAQUE FICHIER ---
        for i, uploaded_file in enumerate(uploaded_files):
            # Mise à jour de la barre de progression
            progress_text = f"Analyse de {uploaded_file.name} ({i+1}/{len(uploaded_files)})..."
            progress_bar.progress((i + 1) / len(uploaded_files), text=progress_text)
            
            text = extract_text_from_pdf(uploaded_file)
            file_contents[uploaded_file.name] = uploaded_file.getvalue()
            
            if text:
                # Appel de la nouvelle fonction pour chaque CV
                single_result = get_single_cv_analysis(text, uploaded_file.name, job_description)
                if single_result:
                    all_results.append(single_result)
                else:
                    st.warning(f"L'analyse du fichier {uploaded_file.name} a échoué. Passage au suivant.")
            else:
                 st.warning(f"Impossible d'extraire le texte de {uploaded_file.name}. Fichier ignoré.")
        
        progress_bar.empty() # On retire la barre de progression à la fin

        if all_results:
            st.subheader("🏆 Classement des Meilleurs Profils")
            
            # Tri des résultats par score, du plus élevé au plus bas
            sorted_results = sorted(all_results, key=lambda x: x.get('score', 0), reverse=True)
            
            for candidate in sorted_results:
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
                        if original_filename and original_filename in file_contents:
                            st.download_button(
                                label="📄 Télécharger le CV",
                                data=file_contents[original_filename],
                                file_name=original_filename,
                                mime="application/pdf",
                                key=f"btn_{original_filename}" # Clé unique pour chaque bouton
                            )
        else:
            # Ce message ne s'affiche que si AUCUN CV n'a pu être analysé
            st.error("L'analyse a échoué pour tous les CV fournis. L'IA n'a pas pu retourner de classement.")