# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
import requests 
import PyPDF2
import json
import io
import time
import traceback
import pandas as pd  # Pour l'export CSV

# --- CONFIGURATION DE LA PAGE ---
# st.set_page_config(
#     page_title="RH+ Pro | Analyse Multi-CV",
#     page_icon="📄",
#     layout="wide"
# )

# --- INITIALISATION DU SESSION STATE ---
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'file_contents' not in st.session_state:
    st.session_state.file_contents = {}
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

# --- FONCTIONS CLÉS ---

@st.cache_data
def convert_df_to_csv(df):
    """Convertit un DataFrame en CSV pour le téléchargement."""
    return df.to_csv(index=False, encoding='utf-8-sig')

def extract_text_from_pdf(file_object):
    """Extrait le texte d'un objet fichier PDF avec validation."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_object)
        text = "".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        if text.strip():
            return text.strip()
        else:
            st.warning(f"Le PDF {file_object.name} semble vide ou illisible.")
            return None
    except Exception as e:
        st.error(f"Erreur d'extraction PDF pour {file_object.name}: {e}")
        return None

def get_single_cv_analysis(cv_text, filename, job_description_text):
    """
    Envoie UN SEUL CV à l'API pour une ANALYSE APPROFONDIE (type RH Senior + ATS).
    """
    try:
        max_cv_length = 4000
        max_job_length = 2000
        cv_text_truncated = cv_text[:max_cv_length]
        job_desc_truncated = job_description_text[:max_job_length]
        
        # --- NOUVEAU PROMPT BASÉ SUR TON RAPPORT ---
        prompt = f"""Tu es un expert en recrutement senior et un simulateur d'ATS. Tu dois analyser le CV fourni par rapport à la description de poste, en te basant sur les meilleures pratiques RH (analyse de mots-clés, quantification, détection de "red flags").

DESCRIPTION DU POSTE (cible) :
{job_desc_truncated}

CV DU CANDIDAT (fichier: {filename}):
{cv_text_truncated}

INSTRUCTIONS D'ANALYSE :
Tu dois évaluer le CV sur deux axes :
1.  **Analyse "Humaine" (Recruteur)** : Évalue l'impact, la cohérence et le potentiel.
2.  **Analyse "Machine" (ATS)** : Simule une analyse de mots-clés et de structure.

INSTRUCTIONS DE FORMATAGE (JSON STRICT) :
Réponds UNIQUEMENT avec un objet JSON valide. L'objet doit contenir les clés suivantes :

1.  "nom_fichier": "{filename}"
2.  "nom": Le nom complet du candidat.
3.  "score": Un score de 0 à 100 basé sur l'adéquation globale (compétences, expérience, potentiel).
4.  "resume": Un résumé court (2-3 lignes) du profil pour un recruteur (le "scan de 30 secondes").
5.  "points_forts": Une liste de 3 points forts MAJEURS pour ce poste (basés sur l'expérience et l'impact).
6.  "points_faibles_ou_risques": Une liste de 2-3 "Red Flags" ou faiblesses (ex: "Job-hopping récent", "Aucune quantification des résultats", "Compétence clé X manquante", "Période d'inactivité inexpliquée").
7.  "elements_quantifies": Une liste de 2-3 exemples de réalisations chiffrées trouvées dans le CV (ex: "Augmentation du CA de 25%", "Gestion d'une équipe de 5 personnes"). Si aucun, retourne ["Aucune quantification notable"].
8.  "analyse_ats": Un objet JSON imbriqué contenant :
    * "mots_cles_trouves": Une liste de 5-7 mots-clés importants de l'offre D'ABORD, puis trouvés dans le CV.
    * "mots_cles_manquants": Une liste de 3-5 mots-clés importants de l'offre NON trouvés dans le CV.
    * "stabilite": Un court avis (1 ligne) sur la stabilité du parcours (ex: "Bonne stabilité globale" ou "Parcours très instable (job-hopping)").
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
            "https://openrouter.ai/api/v1/chat/completions", # <-- CORRIGÉ ICI
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
                
                # --- VÉRIFICATION DES NOUVEAUX CHAMPS ---
                required_fields = [
                    'nom_fichier', 'nom', 'score', 'resume', 
                    'points_forts', 'points_faibles_ou_risques',
                    'elements_quantifies', 'analyse_ats'
                ]
                
                if all(field in parsed_json for field in required_fields) and \
                   'mots_cles_trouves' in parsed_json['analyse_ats'] and \
                   'mots_cles_manquants' in parsed_json['analyse_ats'] and \
                   'stabilite' in parsed_json['analyse_ats']:
                    
                    return parsed_json
                else:
                    st.warning(f"JSON incomplet ou mal structuré pour {filename}. Champs manquants.")
                    st.json(parsed_json) # Pour déboguer
                    return None
                    
            except json.JSONDecodeError:
                st.error(f"Format JSON invalide pour {filename}. Réponse brute :")
                st.code(raw_response)
                return None
        else:
            st.error(f"Erreur API ({response.status_code}) pour {filename}: {response.text}")
            return None

    except Exception as e:
        st.warning(f"L'analyse de {filename} a échoué (Raison: {e}). Passage au suivant.")
        traceback.print_exc()
        return None

# --- INTERFACE UTILISATEUR (UI) ---

with st.sidebar:
    st.title("RH+ Pro")
    st.markdown("---")
    
    with st.expander("Mode d'emploi", expanded=False):
        st.info(
            """
            1.  **Collez** l'offre d'emploi dans le champ "Description du Poste".
            2.  **Chargez** un ou plusieurs CV au format PDF.
            3.  **Cliquez** sur "Analyser" et consultez les résultats.
            """
        )

    st.header("1. Description du Poste")
    job_description = st.text_area(
        label="Collez ici l'offre d'emploi complète",
        height=250, 
        disabled=st.session_state.is_running,
        placeholder="Exemple : 'Recherche Développeur Python Junior...'"
    )

    st.header("2. CV des Candidats")
    uploaded_files = st.file_uploader(
        label="Chargez un ou plusieurs CV au format PDF",
        type="pdf",
        accept_multiple_files=True,
        disabled=st.session_state.is_running 
    )

st.title("Synthèse de l'Analyse")
st.markdown("Optimisez votre présélection. Chargez plusieurs CV, analysez-les en quelques secondes et identifiez les meilleurs talents.")

st.markdown("")
analyze_button = st.button(
    "Analyser les Candidatures", 
    type="primary", 
    use_container_width=True,
    disabled=st.session_state.is_running
)
st.markdown("---")


# --- LOGIQUE DE TRAITEMENT ---
if analyze_button:
    if not job_description.strip():
        st.warning("Veuillez fournir une description de poste.")
    elif not uploaded_files:
        st.warning("Veuillez charger au moins un CV.")
    else:
        st.session_state.is_running = True
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
        st.session_state.is_running = False
        st.rerun()

# --- AFFICHAGE DES RÉSULTATS (ENTIÈREMENT REFAIT) ---
if st.session_state.analysis_done:
    if st.session_state.all_results:
        
        sorted_results = sorted(st.session_state.all_results, key=lambda x: x.get('score', 0), reverse=True)
        
        # --- EXPORT CSV AMÉLIORÉ ---
        try:
            df = pd.json_normalize(sorted_results)
            # Nettoyer les listes pour le CSV
            for col in ['points_forts', 'points_faibles_ou_risques', 'elements_quantifies', 'analyse_ats.mots_cles_trouves', 'analyse_ats.mots_cles_manquants']:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: "; ".join(x) if isinstance(x, list) else x)
            
            csv_data = convert_df_to_csv(df)
            
            st.download_button(
                label="Exporter tous les résultats (CSV)",
                data=csv_data,
                file_name=f"analyse_cv_complete_{time.strftime('%Y%m%d_%H%M')}.csv",
                mime='text/csv',
                use_container_width=True
            )
            st.markdown("---")
        except Exception as e:
            st.error(f"Erreur lors de la préparation de l'export CSV : {e}")

        
        st.subheader(f"Classement des {len(sorted_results)} Profils Analysés")
        
        for i, candidate in enumerate(sorted_results): 
            score = candidate.get('score', 0)
            nom = candidate.get('nom', 'N/A')
            nom_fichier = candidate.get('nom_fichier', 'N/A')

            with st.container(border=True):
                # --- EN-TÊTE ---
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"### {i+1}. {nom} ({nom_fichier})")
                    st.markdown(f"**Résumé (Scan 30s) :** *{candidate.get('resume', 'N/A')}*")
                
                with col2:
                    st.metric(label="Score d'Adéquation", value=f"{score}%")
                    original_filename = candidate.get('nom_fichier')
                    if original_filename and original_filename in st.session_state.file_contents:
                        st.download_button(
                            label="Télécharger le CV",
                            data=st.session_state.file_contents[original_filename],
                            file_name=original_filename,
                            mime="application/pdf",
                            key=f"btn_{original_filename}_{i}" 
                        )
                
                st.markdown("---")
                
                # --- NOUVEAUX ONGLETS D'ANALYSE ---
                tab1, tab2 = st.tabs(["Synthèse Recruteur", "Simulation ATS & Mots-clés"])

                with tab1:
                    st.subheader("Analyse Humaine (Potentiel & Risques)")
                    
                    # Points Forts
                    st.markdown("**Points Forts :**")
                    points_forts = candidate.get('points_forts', [])
                    if points_forts:
                        for point in points_forts: st.markdown(f"- {point}")
                    
                    # Red Flags
                    st.markdown("**Points Faibles / Risques (Red Flags) :**")
                    points_faibles = candidate.get('points_faibles_ou_risques', [])
                    if points_faibles:
                        for point in points_faibles: st.warning(point, icon="🚩")
                    
                    # Quantification
                    st.markdown("**Indicateurs de Performance (Quantification) :**")
                    elements_quantifies = candidate.get('elements_quantifies', ["Aucune quantification notable"])
                    if elements_quantifies[0] != "Aucune quantification notable":
                        for point in elements_quantifies: st.success(point, icon="📈")
                    else:
                        st.info("Aucune réalisation chiffrée notable détectée.")

                with tab2:
                    st.subheader("Analyse Machine (ATS & Stabilité)")
                    ats_data = candidate.get('analyse_ats', {})
                    
                    col_ats1, col_ats2 = st.columns(2)
                    
                    with col_ats1:
                        st.markdown("**Mots-clés de l'offre TROUVÉS :**")
                        mots_cles_trouves = ats_data.get('mots_cles_trouves', [])
                        if mots_cles_trouves:
                            st.success(f"{', '.join(mots_cles_trouves)}", icon="✅")
                        
                        st.markdown("**Stabilité du Parcours :**")
                        st.info(f"{ats_data.get('stabilite', 'N/A')}", icon="⏳")
                        
                    with col_ats2:
                        st.markdown("**Mots-clés de l'offre MANQUANTS :**")
                        mots_cles_manquants = ats_data.get('mots_cles_manquants', [])
                        if mots_cles_manquants:
                            st.error(f"{', '.join(mots_cles_manquants)}", icon="❌")

                        
    elif not st.session_state.is_running:
        st.error("L'analyse a échoué ou n'a retourné aucun résultat valide.")

elif not st.session_state.is_running:
    st.info("Veuillez remplir la description du poste et charger des CV dans le panneau de gauche, puis cliquez sur 'Analyser'.")