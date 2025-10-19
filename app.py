# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
import requests 
import PyPDF2
import json
import io
import time
import traceback

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="RH+ Pro | Analyse Multi-CV",
    page_icon="🚀",
    layout="wide"
)

# --- INITIALISATION DU SESSION STATE ---
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'file_contents' not in st.session_state:
    st.session_state.file_contents = {}
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# --- FONCTIONS CLÉS ---

def extract_text_from_pdf(file_object):
    """Extrait le texte d'un objet fichier PDF avec validation."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = "".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        if text.strip():
            return text.strip()
        else:
            st.warning(f"⚠️ Le PDF {file_object.name} semble vide ou illisible.")
            return None
    except Exception as e:
        st.error(f"❌ Erreur d'extraction PDF pour {file_object.name}: {e}")
        return None

def get_single_cv_analysis(cv_text, filename, job_description_text):
    """
    Envoie UN SEUL CV à l'API via un appel direct avec 'requests' pour plus de robustesse.
    """
    try:
        # Limitation de la taille du texte
        max_cv_length = 4000
        max_job_length = 2000
        cv_text_truncated = cv_text[:max_cv_length]
        job_desc_truncated = job_description_text[:max_job_length]
                        
        prompt = f"""Tu es un expert en recrutement. Analyse UNIQUEMENT le CV ci-dessous par rapport à la description de poste.

DESCRIPTION DU POSTE :
{job_desc_truncated}

CV DU CANDIDAT (fichier: {filename}):
{cv_text_truncated}

INSTRUCTIONS :
1. Lis attentivement LE CV FOURNI CI-DESSUS.
2. Extrais le nom complet du candidat.
3. Calcule un score de 0 à 100 basé sur la correspondance réelle. Puisqu'il s'agit souvent de postes pour des juniors ou des alternants, accorde de l'importance aux compétences transférables et au potentiel d'apprentissage.
4. Rédige un résumé court (2 lignes) du profil RÉEL du candidat.
5. Liste 3 points forts pertinents.
Réponds UNIQUEMENT avec un objet JSON valide (pas de texte avant/après). Le JSON doit contenir les clés "nom_fichier", "nom", "score", "resume", "points_forts".
"""
        
        headers = {
            "Authorization": f"Bearer {st.secrets['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=180
        )

        if response.status_code == 200:
            response_data = response.json()
            raw_response = response_data['choices'][0]['message']['content'].strip()
            
            try:
                if raw_response.startswith("```json"):
                    raw_response = raw_response[7:-3].strip()
                
                parsed_json = json.loads(raw_response)
                
                required_fields = ['nom_fichier', 'nom', 'score', 'resume', 'points_forts']
                if all(field in parsed_json for field in required_fields):
                    return parsed_json
                else:
                    st.warning(f"⚠️ JSON incomplet pour {filename}")
                    return None
            except json.JSONDecodeError:
                st.error(f"❌ Format JSON invalide pour {filename}. Réponse brute :")
                st.code(raw_response)
                return None
        else:
            st.error(f"❌ Erreur API ({response.status_code}) pour {filename}: {response.text}")
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
        st.session_state.all_results = []
        st.session_state.file_contents = {}
        st.session_state.analysis_done = True 
        
        progress_bar = st.progress(0, text="Initialisation de l'analyse...")
        
        for i, uploaded_file in enumerate(uploaded_files):
            progress_text = f"Analyse de {uploaded_file.name} ({i+1}/{len(uploaded_files)})..."
            progress_bar.progress((i + 1) / len(uploaded_files), text=progress_text)
            
            file_bytes = uploaded_file.getvalue()
            st.session_state.file_contents[uploaded_file.name] = file_bytes
            
            text = extract_text_from_pdf(io.BytesIO(file_bytes))
            
            if text:
                single_result = get_single_cv_analysis(text, uploaded_file.name, job_description)
                if single_result:
                    st.session_state.all_results.append(single_result)
        
        progress_bar.empty()

# --- AFFICHAGE DES RÉSULTATS ---
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
                    
                    if original_filename and original_filename in st.session_state.file_contents:
                        st.download_button(
                            label="📄 Télécharger le CV",
                            data=st.session_state.file_contents[original_filename],
                            file_name=original_filename,
                            mime="application/pdf",
                            key=f"btn_{original_filename}_{i}" 
                        )
    else:
        st.error("L'analyse a échoué ou n'a retourné aucun résultat valide.")