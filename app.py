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
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'file_contents' not in st.session_state:
    st.session_state.file_contents = {}
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# --- FONCTIONS CLÉS ---

# Correction 1 : Améliorer l'extraction PDF avec debugging
def extract_text_from_pdf(file_object):
    """Extrait le texte d'un objet fichier PDF avec validation."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = ""
        # Extraction page par page avec vérification
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
                
        if text.strip():
            # DEBUG : Afficher un aperçu du texte extrait
            st.info(f"✅ Texte extrait : {len(text)} caractères. Aperçu : {text[:200]}...")
            return text.strip()
        else:
            st.warning("⚠️ Le PDF semble vide ou illisible.")
            return None
    except Exception as e:
        st.error(f"❌ Erreur d'extraction PDF : {e}")
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
        
        # Correction 2 : Limiter la taille du texte et améliorer le prompt
        
        # Limitation de la taille du texte pour éviter les dépassements de tokens
        max_cv_length = 3000  # Limite à ~3000 caractères pour le CV
        max_job_length = 1500  # Limite à ~1500 caractères pour la description
                
        cv_text_truncated = cv_text[:max_cv_length] if len(cv_text) > max_cv_length else cv_text
        job_desc_truncated = job_description_text[:max_job_length] if len(job_description_text) > max_job_length else job_description_text
                
        # DEBUG : Afficher ce qui est envoyé à l'API
        st.write(f"📤 Envoi à l'API - Fichier: {filename}")
        st.write(f"   - Longueur CV: {len(cv_text_truncated)} caractères")
        st.write(f"   - Longueur description: {len(job_desc_truncated)} caractères")
                
        prompt = f"""Tu es un expert en recrutement. Analyse UNIQUEMENT le CV ci-dessous par rapport à la description de poste.

DESCRIPTION DU POSTE :
{job_desc_truncated}

CV DU CANDIDAT (fichier: {filename}):
{cv_text_truncated}

INSTRUCTIONS :
1. Lis attentivement LE CV FOURNI CI-DESSUS
2. Extrais le nom du candidat du CV
3. Calcule un score de 0 à 100 basé sur la correspondance réelle
4. Rédige un résumé court (2 lignes) du profil RÉEL du candidat
5. Liste 3 points forts pertinents
Réponds UNIQUEMENT avec ce JSON (pas de texte avant/après) :
{{
    "nom_fichier": "{filename}",
    "nom": "Nom extrait du CV",
    "score": 75,
    "resume": "Résumé du profil réel...",
    "points_forts": ["Point 1", "Point 2", "Point 3"]
}}
"""

        response = client.chat.completions.create(
            # CORRECTION : Remplacement par le modèle Gemini gratuit et stable
            model="google/gemini-2.0-flash-exp:free",
            # --- ALTERNATIVE (si Gemini échoue aussi) ---
            # model="deepseek/deepseek-r1-distill-llama-70b:free",
            
            messages=[{"role": "user", "content": prompt}],
            # Note : response_format est retiré car le prompt le gère
        )
        
        # Correction 3 : Ajouter du debugging après l'appel API
        if response.choices and response.choices[0].message.content:
            raw_response = response.choices[0].message.content.strip()
                        
            # DEBUG : Afficher la réponse brute de l'API
            with st.expander(f"🔍 Réponse brute de l'API pour {filename}"):
                st.code(raw_response)
                        
            try:
                # Nettoyage des balises markdown si présentes
                if raw_response.startswith("```json"):
                    raw_response = raw_response[7:-3].strip()
                elif raw_response.startswith("```"):
                    raw_response = raw_response[3:-3].strip()
                
                # S'assurer que la réponse commence bien par { (début d'un JSON)
                if not raw_response.startswith("{"):
                    st.error(f"❌ L'IA n'a pas retourné un JSON pour {filename} (commence par '{raw_response[0]}').")
                    return None

                parsed_json = json.loads(raw_response)
                                
                # Validation que le JSON contient les champs requis
                required_fields = ['nom_fichier', 'nom', 'score', 'resume', 'points_forts']
                if all(field in parsed_json for field in required_fields):
                    st.success(f"✅ Analyse réussie pour {filename}")
                    return parsed_json
                else:
                    st.warning(f"⚠️ JSON incomplet pour {filename}")
                    return None
                                
            except json.JSONDecodeError as je:
                st.error(f"❌ Format JSON invalide pour {filename}")
                st.code(raw_response)
                return None
        else:
            return None

    except Exception as e:
        st.warning(f"L'analyse de {filename} a échoué (Raison: {e}). Passage au suivant.")
        traceback.print_exc()
        return None

# --- INTERFACE UTILISATEUR (UI) ---
st.title("🚀 RH+ Pro (Mode Débogage)")
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
            
            # Appel de la fonction d'extraction (qui contient maintenant des st.info)
            text = extract_text_from_pdf(io.BytesIO(file_bytes))
            
            if text:
                # Appel de la fonction d'analyse (qui contient st.write, st.expander, etc.)
                single_result = get_single_cv_analysis(text, uploaded_file.name, job_description)
                if single_result:
                    st.session_state.all_results.append(single_result)
            # Pas de 'else' ici, car extract_text_from_pdf gère ses propres messages d'erreur
        
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
        st.error("L'analyse a échoué ou n'a retourné aucun résultat valide. Vérifiez les messages de débogage ci-dessus.")