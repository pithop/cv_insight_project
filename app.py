# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
from openai import OpenAI # On utilise la bibliothèque OpenAI, compatible avec OpenRouter
import PyPDF2
import os

# --- FONCTIONS CLÉS ---

def extract_text_from_pdf(file_object):
    """
    Extraire le texte d'un objet fichier PDF téléchargé.
    """
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier PDF : {e}")
        return None

def get_openrouter_analysis(cv_text, job_description_text):
    """
    Envoyer le CV et la description de poste à l'API OpenRouter pour analyse.
    Cette fonction utilise la bibliothèque OpenAI qui est compatible avec l'API d'OpenRouter.
    """
    try:
        # Configuration du client pour pointer vers l'API OpenRouter
        client = OpenAI(
          base_url="https://openrouter.ai/api/v1",
          api_key=st.secrets["OPENROUTER_API_KEY"],
        )
        
        # --- PROMPT AMÉLIORÉ ET STRICT ---
        # Instructions très directes pour éviter que l'IA ne dialogue au lieu de travailler.
        prompt = f"""
        Votre unique rôle est d'agir comme un analyseur IA de CV. Votre mission est de générer un rapport d'analyse en comparant le CV et la description de poste.

        CV DU CANDIDAT :
        ---
        {cv_text}
        ---

        DESCRIPTION DU POSTE :
        ---
        {job_description_text}
        ---

        INSTRUCTIONS STRICTES :
        1. Votre réponse doit être UNIQUEMENT en français.
        2. Générez un rapport au format Markdown en utilisant EXACTEMENT les titres et la structure suivants.

        ### 📝 Synthèse Exécutive
        (Un résumé percutant en 3 points : le profil en une phrase, la force majeure, et le principal point de vigilance.)

        ### 🎯 Analyse d'Adéquation Détaillée
        **Compétences Techniques :** (Évaluez la correspondance des technologies, langages, frameworks. Soyez précis et citez des exemples.)
        **Expérience Professionnelle :** (Analysez la pertinence des expériences passées, des projets et des responsabilités par rapport au poste.)

        ### ⚠️ Points de Vigilance et Questions Stratégiques
        (Identifiez les zones d'ombre, les manques potentiels et suggérez 3 questions précises et pertinentes à poser en entretien pour clarifier ces points.)

        ### 📊 Tableau de Score Détaillé
        (Créez un tableau Markdown avec les colonnes : "Critère", "Score (/100)", et "Justification Courte". Soyez objectif dans votre notation.)
        | Critère | Score (/100) | Justification Courte |
        | :--- | :--- | :--- |
        | Compétences Techniques | ... | ... |
        | Expérience Pertinente | ... | ... |
        | **Score Global d'Alignement** | **...** | **...** |

        ### ⭐ Recommandation Finale
        (Donnez une recommandation claire et actionnable : "À rencontrer en priorité", "Potentiel intéressant à explorer", ou "Ne correspond pas aux critères essentiels".)

        ---
        Générez UNIQUEMENT le rapport Markdown ci-dessus. N'ajoutez AUCUN commentaire, explication ou texte d'introduction.
        """

        # Appel à l'API via le client configuré
        response = client.chat.completions.create(
          # SOLUTION DÉFINITIVE : On utilise un modèle stable hébergé par un fournisseur fiable.
          model="google/gemma-2-9b-it:free", 
          messages=[
            {
              "role": "user",
              "content": prompt,
            },
          ],
        )
        # AMÉLIORATION : Vérification pour s'assurer que la réponse n'est pas vide
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            st.error("L'API a retourné une réponse vide. Le modèle n'a peut-être pas pu générer d'analyse.", icon="🤷")
            return "Aucun résultat généré."

    except Exception as e:
        st.error(f"Une erreur est survenue lors de l'appel à l'API OpenRouter : {e}", icon="🚨")
        return "L'analyse n'a pas pu être complétée. Vérifiez votre clé d'API OpenRouter et que le modèle choisi est correct."

# --- CONFIGURATION DE L'APPLICATION STREAMLIT ---
st.set_page_config(
    page_title="CV-Insight (OpenRouter)",
    page_icon="📄",
    layout="wide"
)

# --- INTERFACE UTILISATEUR (UI) ---
st.title("CV-Insight : Assistant de Présélection IA 🤖")
st.markdown("Propulsé par **OpenRouter**")
st.markdown("---")

# Création de deux colonnes pour l'interface
col1, col2 = st.columns(2)

with col1:
    st.header("📄 CV du Candidat")
    uploaded_cv = st.file_uploader("Chargez le CV au format PDF", type="pdf")

with col2:
    st.header("📋 Description du Poste")
    job_description = st.text_area("Collez ici l'offre d'emploi", height=300)

# Bouton d'analyse centré
st.markdown("<br>", unsafe_allow_html=True)
col_btn1, col_btn2, col_btn3 = st.columns([2,3,2])
with col_btn2:
    analyze_button = st.button("✨ Lancer l'Analyse ✨", use_container_width=True)

st.markdown("---")

# --- LOGIQUE DE TRAITEMENT ---
if analyze_button:
    if uploaded_cv is not None and job_description:
        with st.spinner("Analyse en cours via OpenRouter... L'IA réfléchit 🧠"):
            cv_text = extract_text_from_pdf(uploaded_cv)
            
            # --- AMÉLIORATION CLÉ ---
            # Vérifier si du texte a bien été extrait du PDF. Le .strip() retire les espaces vides.
            if cv_text and cv_text.strip():
                analysis_result = get_openrouter_analysis(cv_text, job_description)
                st.subheader("✅ Analyse Complétée")
                st.markdown(analysis_result)
            else:
                # Si aucun texte n'est extrait, on affiche un message d'erreur clair à l'utilisateur
                st.error("Impossible d'extraire le contenu textuel de ce CV. Le fichier PDF est peut-être une image scannée ou utilise un format non supporté. Essayez avec un autre CV au format texte.", icon="⚠️")
    else:
        st.warning("Veuillez charger un CV et fournir une description de poste.", icon="💡")
