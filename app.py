# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
from openai import OpenAI
import PyPDF2
import json
import io # Importation nécessaire pour les téléchargements

# --- CONFIGURATION DE LA PAGE ---
# On change le titre et l'icône de la page
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
        # Correction : s'assurer que le texte n'est pas None avant de joindre
        text = "".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        return text
    except Exception:
        # Simplification de la gestion d'erreur
        return None

def get_multi_cv_analysis(cv_data_list, job_description_text):
    """
    Envoie une liste de CV à l'API OpenRouter pour une analyse et un classement.
    """
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=st.secrets["OPENROUTER_API_KEY"],
        )
        
        # Le prompt est maintenant conçu pour gérer plusieurs CV et renvoyer une structure JSON
        prompt = f"""
        En tant qu'expert en recrutement IA, votre mission est d'analyser une liste de CV par rapport à une description de poste.
        Vous devez évaluer chaque candidat, extraire leurs informations clés, leur attribuer un score de compatibilité, et les classer.

        DESCRIPTION DU POSTE :
        ---
        {job_description_text}
        ---

        LISTE DES CV (nom de fichier et contenu) :
        ---
        {json.dumps(cv_data_list, indent=2)}
        ---

        INSTRUCTIONS STRICTES :
        1. Analysez chaque CV de la liste fournie. Utilisez le "nom_fichier" pour identifier le CV dans votre analyse.
        2. Pour chaque CV, déterminez un score de compatibilité global sur 100.
        3. Extrayez le nom complet du candidat (si possible, sinon utilisez le nom du fichier).
        4. Rédigez un résumé très court (2 lignes max) du profil.
        5. Listez les 3 points forts principaux qui correspondent à l'offre.
        6. Renvoyez votre analyse sous la forme d'un unique objet JSON. N'ajoutez AUCUN autre texte ou explication.
        7. Le JSON doit être une liste d'objets, où chaque objet représente un candidat et contient les clés suivantes : "nom_fichier", "nom", "score", "resume", "points_forts".
        8. Classez les candidats dans la liste JSON du score le plus élevé au plus bas.

        Exemple de format de sortie JSON attendu :
        [
          {{
            "nom_fichier": "cv_jean_dupont.pdf",
            "nom": "Jean Dupont",
            "score": 92,
            "resume": "Développeur Full-Stack avec 5 ans d'expérience sur Python et React. Spécialisé dans les applications SaaS.",
            "points_forts": [
              "Excellente maîtrise de Python/Django requise pour le backend.",
              "Expérience avérée en développement front-end avec React.",
              "Participation à des projets similaires dans le secteur du SaaS."
            ]
          }},
          {{
            "nom_fichier": "cv_marie_curie.pdf",
            "nom": "Marie Curie",
            "score": 85,
            "resume": "Ingénieure logicielle spécialisée en data science. Compétences solides en Python mais moins d'expérience sur le front-end.",
            "points_forts": [
              "Maîtrise approfondie de Python et de ses librairies data.",
              "Capacité à gérer des projets complexes de A à Z.",
              "Bonne compréhension des architectures logicielles."
            ]
          }}
        ]
        """

        response = client.chat.completions.create(
            model="google/gemma-2-9b-it:free",
            response_format={"type": "json_object"}, # On demande explicitement un JSON
            messages=[{"role": "user", "content": prompt}],
        )
        
        if response.choices and response.choices[0].message.content:
            json_response_str = response.choices[0].message.content
            if json_response_str.startswith("```json"):
                json_response_str = json_response_str[7:-3].strip()
            return json.loads(json_response_str)
        else:
            return None

    except Exception as e:
        st.error(f"Une erreur est survenue lors de l'appel à l'API : {e}")
        return None

# --- INTERFACE UTILISATEUR (UI) AMÉLIORÉE ---

# Titre et introduction
st.title("🚀 RH+ Pro")
st.markdown("Optimisez votre présélection. Chargez plusieurs CV, analysez-les en quelques secondes et identifiez les meilleurs talents.")
st.markdown("---")

# Changement de la mise en page : plus de colonnes pour les inputs
st.subheader("1. Description du Poste")
job_description = st.text_area("Collez ici l'offre d'emploi complète", height=250, label_visibility="collapsed")

# Changement ici : accept_multiple_files=True
st.subheader("2. CV des Candidats")
uploaded_files = st.file_uploader(
    "Chargez un ou plusieurs CV au format PDF",
    type="pdf",
    accept_multiple_files=True,
    label_visibility="collapsed"
)

# Bouton d'analyse
st.markdown("") # Espace
analyze_button = st.button("Analyser les Candidatures", type="primary", use_container_width=True)
st.markdown("---")

# --- LOGIQUE DE TRAITEMENT ET AFFICHAGE DES RÉSULTATS ---
if analyze_button:
    # Vérification des inputs
    if not job_description.strip():
        st.warning("⚠️ Veuillez fournir une description de poste.")
    elif not uploaded_files: # Vérifie si la liste n'est pas vide
        st.warning("⚠️ Veuillez charger au moins un CV.")
    else:
        with st.spinner("Analyse en cours... L'IA évalue et classe les profils..."):
            cv_data = []
            file_contents = {} # Dictionnaire pour stocker le contenu des fichiers
            
            # Boucle sur tous les fichiers chargés
            for uploaded_file in uploaded_files:
                text = extract_text_from_pdf(uploaded_file)
                if text:
                    cv_data.append({"nom_fichier": uploaded_file.name, "texte_cv": text})
                    # Stocker le contenu binaire pour le téléchargement
                    file_contents[uploaded_file.name] = uploaded_file.getvalue()
            
            if not cv_data:
                st.error("❌ Aucun texte n'a pu être extrait des CV fournis. Assurez-vous qu'ils ne sont pas des images scannées.")
            else:
                # Appel de la nouvelle fonction d'analyse
                analysis_results = get_multi_cv_analysis(cv_data, job_description)

                if analysis_results:
                    st.subheader("🏆 Classement des Meilleurs Profils")
                    
                    # Boucle pour afficher chaque candidat dans une carte
                    for i, candidate in enumerate(analysis_results):
                        # Définir la couleur du badge en fonction du score
                        score = candidate.get('score', 0) # Assurer qu'on a un score
                        if score >= 85:
                            badge_icon = "🥇"
                        elif score >= 70:
                            badge_icon = "🥈"
                        else:
                            badge_icon = "🥉"

                        with st.container(border=True):
                            col1, col2 = st.columns([4, 1]) # Colonnes pour la mise en page de la carte
                            with col1:
                                st.markdown(f"### {badge_icon} {candidate.get('nom', 'N/A')} ({candidate.get('nom_fichier', 'N/A')})")
                                st.markdown(f"**Résumé du profil :** {candidate.get('resume', 'N/A')}")
                                st.markdown("**Points forts pour ce poste :**")
                                points_forts = candidate.get('points_forts', ['Aucun point fort spécifique identifié.'])
                                for point in points_forts:
                                    st.markdown(f"- {point}")

                            with col2:
                                st.metric(label="Score d'Alignement", value=f"{score}%")
                                # Ajout du bouton de téléchargement
                                original_filename = candidate.get('nom_fichier')
                                if original_filename and original_filename in file_contents:
                                    st.download_button(
                                        label="📄 Télécharger le CV",
                                        data=file_contents[original_filename],
                                        file_name=original_filename,
                                        mime="application/pdf",
                                    )
                else:
                    st.error("L'analyse a échoué. L'IA n'a pas pu retourner un classement.")