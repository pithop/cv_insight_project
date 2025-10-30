# --- BIBLIOTHÈQUES NÉCESSAIRES ---
import streamlit as st
import requests 
import json
import io
import time
import traceback
import pandas as pd
import re
import os

# --- MOTEUR PDF ROBUSTE ---
import fitz  # PyMuPDF

# --- Imports pour la robustesse ---
import tenacity
from requests.exceptions import RequestException, HTTPError, InvalidSchema # Ajouter InvalidSchema
import logging

# --- Imports pour API ---
from duckduckgo_search import DDGS 
from urllib.parse import urlparse 
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# --- CONFIGURATION LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION DE LA PAGE ---
ICON_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'rh_pro_icon.png')

# Utilise l'icône PNG si elle existe, sinon l'emoji fallback
page_icon_to_use = ICON_PATH if os.path.exists(ICON_PATH) else '🔎'
st.set_page_config(
    page_title="RH+ Pro | Analyse Multi-CV V3",
    page_icon=page_icon_to_use, # Passe juste le chemin (str) ou l'emoji (str)
    layout="wide"
)

# --- INITIALISATION DU SESSION STATE ---
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'file_contents' not in st.session_state: st.session_state.file_contents = {}
if 'analysis_done' not in st.session_state: st.session_state.analysis_done = False
if 'is_running' not in st.session_state: st.session_state.is_running = False

# --- FONCTIONS UTILITAIRES ---

@st.cache_data
def convert_df_to_csv(df):
    """Convertit un DataFrame en CSV pour le téléchargement, gérant listes/dict."""
    if df.empty: return ""
    try:
        df_copy = df.copy()
        for col in df_copy.columns:
            if col in df_copy.columns and not df_copy[col].dropna().empty:
                 first_valid = df_copy[col].dropna().iloc[0]
                 if isinstance(first_valid, (list, dict)):
                      df_copy[col] = df_copy[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else str(x))
                 else:
                      df_copy[col] = df_copy[col].astype(str)
            else:
                 df_copy[col] = df_copy[col].astype(str)
                 
        return df_copy.to_csv(index=False, encoding='utf-8-sig')
    except Exception as e:
        st.error(f"Erreur conversion CSV: {e}")
        try: return df.to_string(index=False) 
        except: return ""

# --- ÉTAPE 0: EXTRACTION PDF (PyMuPDF) ---
def extract_text_from_pdf(file_bytes_io, filename):
    """Extrait et nettoie le texte d'un PDF avec PyMuPDF."""
    text = ""
    try:
        with fitz.open(stream=file_bytes_io, filetype="pdf") as doc:
            for page in doc: 
                text += page.get_text("text", sort=True, flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE) + "\n"
        text = text.strip()
        if text:
            text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text) 
            text = re.sub(r'\s*\n\s*', '\n', text) 
            text = re.sub(r'\n{3,}', '\n\n', text) 
            text = re.sub(r'[ \t]{2,}', ' ', text) 
            text = "\n".join(line for line in text.splitlines() if len(line.strip()) > 3 or '@' in line or '+' in line or 'http' in line)
            text = "\n".join(line for line in text.splitlines() if re.search(r'[a-zA-Z0-9]', line)) 
            text = "\n".join(line for line in text.splitlines() if not re.match(r'^[\W_]+$', line.strip())) 
            text = "\n".join(line for line in text.splitlines() if not (line.strip().isdigit() and len(line.strip()) < 4 and len(text.splitlines()) > 10)) 
            return text
        else:
            st.warning(f"PDF {filename} vide ou texte non extractible (PyMuPDF).")
            return None
    except Exception as e:
        st.error(f"Erreur extraction PDF (PyMuPDF) pour {filename}: {e}")
        logger.exception(f"Traceback complet extraction PDF pour {filename}:")
        return None

# --- FONCTION ANALYSE LOCALE (Mots-clés + Stabilité Simple) ---
def perform_local_analysis(cv_text, job_description_text):
    """Effectue une analyse basique locale (mots-clés, tentative stabilité)."""
    analysis = {"mots_cles_trouves": [], "mots_cles_manquants": [], "stabilite": "N/A"}
    try:
        job_keywords = set(re.findall(r'\b[\w\'-]{4,}\b', job_description_text.lower()))
        cv_words = set(re.findall(r'\b[\w\'-]{4,}\b', cv_text.lower()))
        
        if job_keywords: 
             analysis["mots_cles_trouves"] = sorted(list(job_keywords.intersection(cv_words)))[:15] 
             analysis["mots_cles_manquants"] = sorted(list(job_keywords - cv_words))[:10] 
        
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', cv_text) 
        unique_years = sorted(list(set(years)))
        if len(unique_years) > 2: 
             analysis["stabilite"] = f"Potentiel parcours stable ({unique_years[0]} - {unique_years[-1]})"
        elif len(unique_years) > 0:
             analysis["stabilite"] = f"Parcours potentiellement récent (années: {', '.join(unique_years)})"
        else:
             analysis["stabilite"] = "Stabilité difficile à évaluer localement"
             
    except Exception as e:
        logger.error(f"Erreur analyse locale: {e}")
        analysis["stabilite"] = "Erreur analyse locale"
    return analysis

# --- FONCTION FALLBACK ULTIME ---
def get_basic_fallback_info(cv_text, job_description_text, filename):
    """Génère les infos Nom/Score/Résumé si l'IA échoue (utilisée comme fallback)."""
    st.warning(f"Utilisation fallback pour infos Nom/Score/Résumé pour {filename}.", icon="⚠️")
    result = {
        "nom": "Nom (Ext. Basique)", "score": 0,
        "resume_profil": "Analyse IA échouée. Score basé sur mots-clés.", 
        "analysis_type": "Basique + Mots Clés Locaux" 
    }
    try:
        job_keywords = set(re.findall(r'\b[\w\'-]{4,}\b', job_description_text.lower()))
        cv_words = set(re.findall(r'\b[\w\'-]{4,}\b', cv_text.lower()))
        match_percentage = (len(job_keywords.intersection(cv_words)) / len(job_keywords)) * 100 if job_keywords else 0
        result["score"] = min(int(match_percentage), 70) 

        first_lines = "\n".join(cv_text.splitlines()[:5])
        name_match = re.search(r'^([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ\'\-]+(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ\'\-]+)+)', first_lines)
        if name_match: result["nom"] = name_match.group(1).strip() + " (Ext. Basique)"

    except Exception as e:
        st.error(f"Erreur calcul fallback basique pour {filename}: {e}")
        result.update({"nom": "Erreur Fallback", "score": 0, "resume_profil": "Erreur fallback."})
    return result

# --- FONCTION D'APPEL API (OpenRouter UNIQUEMENT + retry + PAUSE 1.5s) ---
@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=3, max=30), 
    stop=tenacity.stop_after_attempt(3),
    # Ajouter InvalidSchema aux erreurs réessayables (au cas où, même si on corrige l'URL)
    retry=tenacity.retry_if_exception_type((RequestException, IOError, HTTPError, ValueError, InvalidSchema)), 
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
    reraise=True
)
def call_openrouter_api(prompt, key_config, max_tokens=2000, temperature=0.1, force_json=False):
    """Appelle l'API OpenRouter via requests, gère retries ET PAUSE de 1.5s."""
    api_key = key_config["key"]
    model = key_config["model"]
    # --- CORRECTION URL ---
    # Assurer que l'URL est une chaîne de caractères correcte SANS crochets
    url = str(key_config["url"]).strip('[]') # Force la conversion en str et supprime les crochets si présents
    # --- FIN CORRECTION ---


    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://rhplus.streamlit.app", # Adaptez si besoin
        "X-Title": "RH+ Pro CV Workflow V3"
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}], 
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    if force_json:
         body["response_format"] = {"type": "json_object"} 
         logger.info(f"Tentative d'appel API avec force_json=True pour {model} à {url}")

    try:
        # Log l'URL juste avant l'appel pour débogage
        logger.info(f"Appel POST vers: {url}")
        response = requests.post(url, headers=headers, json=body, timeout=180)
        
        # Log status code pour débogage même si ce n'est pas une erreur levée par raise_for_status
        logger.info(f"Réponse reçue de {url}: Status {response.status_code}")
        
        response.raise_for_status() # Lève HTTPError pour 4xx/5xx
        response_data = response.json()

        if not isinstance(response_data, dict) or 'choices' not in response_data or not response_data['choices']:
            raise ValueError("Réponse API invalide: 'choices' manquantes ou vides.")
        
        content = response_data['choices'][0].get('message', {}).get('content')
        if content is None:
             raise ValueError("Réponse API invalide: 'content' manquant.")
        
        if 'api_provider_logged' not in st.session_state:
             st.session_state.api_provider_logged = f"OpenRouter ({model})"
             
        time.sleep(1.5) # PAUSE après chaque appel réussi
        return content.strip()

    except InvalidSchema as e_schema: # Attraper spécifiquement l'erreur de schéma
         logger.error(f"ERREUR FATALE: InvalidSchema pour l'URL '{url}'. Vérifiez la définition de l'URL dans api_keys_pool. Erreur: {e_schema}")
         # Ne pas réessayer sur cette erreur, c'est un bug de code
         raise tenacity.DoAttempt # Indique à Tenacity d'arrêter les reessais pour cette cause
    except Exception as e:
        logger.error(f"Erreur appel API OpenRouter ({url}) : {e}")
        if isinstance(e, HTTPError):
            logger.error(f"Status Code: {e.response.status_code}, Response Body: {e.response.text[:500]}")
            if e.response.status_code == 400 and force_json:
                 logger.warning("Erreur 400 avec force_json=True. Modèle incompatible?")
        time.sleep(2.0) 
        raise # Relance pour Tenacity

# --- ÉTAPE 1: Screening IA (JSON) ---
# (Fonction inchangée, utilise call_openrouter_api corrigé)
def call_screening_ia(cv_text, job_desc, key_config):
    """Appelle l'IA pour extraire les infos structurées de base en JSON."""
    prompt = f"""Extrais les informations suivantes du CV par rapport au poste.
    Réponds OBLIGATOIREMENT en format JSON valide avec les clés exactes: "nom", "contact" (objet avec "email", "telephone", "linkedin"), "langues" (liste de strings), "diplome_principal" (string), "annees_experience_estimees" (integer).
    Si une info est absente, utilise null ou une valeur vide appropriée (liste vide, string vide, 0 pour expérience). NE PAS ajouter de commentaires ou texte hors JSON.

    DESCRIPTION POSTE (contexte rapide):
    {job_desc[:1000]}

    CV COMPLET:
    {cv_text[:4000]}

    JSON ATTENDU (exemple):
    {{
      "nom": "Jean Dupont",
      "contact": {{
        "email": "jean.dupont@email.com",
        "telephone": "0612345678",
        "linkedin": "https://linkedin.com/in/jeandupont" 
      }},
      "langues": ["Français (Natif)", "Anglais (C1)"],
      "diplome_principal": "Master Informatique",
      "annees_experience_estimees": 5
    }}

    JSON:
    """
    response_str = None 
    try:
        response_str = call_openrouter_api(prompt, key_config, max_tokens=500, temperature=0.0, force_json=True)
        
        cleaned_json_string = response_str
        if response_str.startswith("```json"): cleaned_json_string = response_str[7:-3].strip()
        elif response_str.startswith("`"): cleaned_json_string = response_str.strip('`')
        
        try: data = json.loads(cleaned_json_string)
        except json.JSONDecodeError:
             logger.warning(f"Screening IA: tentative correction JSON...")
             corrected_json_string = cleaned_json_string.replace('\\_', '_').replace('\\*', '*')
             data = json.loads(corrected_json_string) 

        required_keys = ["nom", "contact", "langues", "diplome_principal", "annees_experience_estimees"]
        if all(key in data for key in required_keys):
             data['contact'] = data.get('contact') if isinstance(data.get('contact'), dict) else {}
             data['langues'] = data.get('langues') if isinstance(data.get('langues'), list) else []
             data['diplome_principal'] = str(data.get('diplome_principal', '')) 
             try:
                 exp_val = data.get('annees_experience_estimees')
                 data['annees_experience_estimees'] = int(exp_val) if exp_val is not None else 0
             except (ValueError, TypeError): data['annees_experience_estimees'] = 0
             return data
        else:
            logger.warning(f"Screening IA JSON incomplet: Clés manquantes dans {cleaned_json_string[:200]}...")
            return None
            
    except json.JSONDecodeError:
        logger.warning(f"Screening IA réponse non JSON (après nettoyage): {cleaned_json_string[:200]}...")
        return None
    except Exception as e:
        logger.error(f"Erreur appel/parsing Screening IA: {e}") 
        return None 

# --- ÉTAPE 2b: Raffinement Mots-Clés IA (JSON) ---
# (Fonction inchangée, utilise call_openrouter_api corrigé)
def call_keyword_refinement_ia(mots_cles_trouves_bruts, mots_cles_manquants_bruts, cv_extrait, job_desc_extrait, key_config):
    """Demande à l'IA de filtrer et prioriser les listes de mots-clés brutes."""
    if not mots_cles_trouves_bruts and not mots_cles_manquants_bruts: return None 
         
    prompt = f"""Tu es un simulateur d'ATS expert. Ta mission est double :
    1.  Nettoyer les listes brutes (supprimer les mots génériques non techniques comme 'semaine', 'article', 'le', 'pour').
    2.  Auditer le CV par rapport aux "Maîtrises indispensables" du poste.

    CONTEXTE POSTE (extrait):
    {job_desc_extrait[:1000]}

    CONTEXTE CV (extrait):
    {cv_extrait[:2000]}

    LISTES BRUTES:
    Trouvés: {', '.join(mots_cles_trouves_bruts)}
    Manquants: {', '.join(mots_cles_manquants_bruts)}

    ### RÈGLES DE SORTIE OBLIGATOIRES ###
    1.  **JSON Valide :** Tu DOIS répondre en JSON (clés "mots_cles_trouves_filtres", "mots_cles_manquants_prioritaires").
    2.  **Limite :** Limite chaque liste à 10 éléments.
    3.  **AUDIT INDISPENSABLES :** Regarde le CONTEXTE POSTE. Trouve la ligne "Maîtrises indispensables". Pour chaque technologie listée (ex: Laravel, Vue.js, NuxtJS, Tailwind), si elle est absente des "Trouvés" ET du "CV", elle DOIT être ajoutée à "mots_cles_manquants_prioritaires". C'est ta priorité absolue.

    JSON ATTENDU (exemple):
    {{
      "mots_cles_trouves_filtres": ["php", "sql", "git", "api"],
      "mots_cles_manquants_prioritaires": ["laravel", "vue.js", "nuxtjs", "tailwind", "ci/cd"] 
    }}

    JSON:
    """
    response_str = None 
    try:
        response_str = call_openrouter_api(prompt, key_config, max_tokens=400, temperature=0.1, force_json=True)
        
        cleaned_json_string = response_str
        if response_str.startswith("```json"): cleaned_json_string = response_str[7:-3].strip()
        elif response_str.startswith("`"): cleaned_json_string = response_str.strip('`')

        try: data = json.loads(cleaned_json_string)
        except json.JSONDecodeError:
             logger.warning(f"Raffinement Mots-clés: tentative correction JSON...")
             corrected_json_string = cleaned_json_string.replace('\\_', '_').replace('\\*', '*')
             data = json.loads(corrected_json_string)

        required_keys = ["mots_cles_trouves_filtres", "mots_cles_manquants_prioritaires"]
        if all(key in data for key in required_keys) and isinstance(data["mots_cles_trouves_filtres"], list) and isinstance(data["mots_cles_manquants_prioritaires"], list):
            data["mots_cles_trouves_filtres"] = data["mots_cles_trouves_filtres"][:10]
            data["mots_cles_manquants_prioritaires"] = data["mots_cles_manquants_prioritaires"][:10]
            return data
        else:
            logger.warning(f"Raffinement Mots-clés JSON incomplet: {cleaned_json_string[:200]}...")
            return None
            
    except json.JSONDecodeError:
        logger.warning(f"Raffinement Mots-clés réponse non JSON (après nettoyage): {cleaned_json_string[:200]}...")
        return None
    except Exception as e:
        logger.error(f"Erreur appel/parsing Raffinement Mots-clés IA: {e}")
        return None

# --- ÉTAPE 3: Analyse Qualitative IA (JSON) ---
# (Fonction inchangée, utilise call_openrouter_api corrigé)
def call_qualitative_ia(cv_text, job_desc, screening_data, key_config):
    """Demande l'analyse qualitative (score, résumé, forces/faiblesses)."""
    screening_info_str = json.dumps(screening_data, indent=2, ensure_ascii=False) if screening_data else "Non disponible (Étape 1 échouée)"

    # NOUVEAU PROMPT AMÉLIORÉ
    prompt = f"""Tu es un manager technique expérimenté évaluant un CV pour le poste de Développeur Web Full-stack.
    L'offre a des "Maîtrises indispensables" claires : PHP (Laravel), SQL, Javascript (Vue.js / NuxtJS), CSS (Tailwind), Git.
    
    Réponds OBLIGATOIREMENT en format JSON valide avec les clés exactes: "score" (integer 0-100), "resume_profil" (string 2-3 phrases), "points_forts_cles" (liste), "points_faibles_risques" (liste), "adequation_poste" (string 1 phrase), et "evaluation_technologies_cles" (string 1-2 phrases). NE PAS inclure de texte hors JSON.

    DESCRIPTION POSTE:
    {job_desc[:1500]}

    INFORMATIONS FACTUELLES EXTRAITES:
    {screening_info_str}

    CV COMPLET (pour contexte détaillé):
    {cv_text[:5000]}

    ### INSTRUCTIONS SPÉCIFIQUES POUR LES CLÉS ###
    - "score": Basé sur l'adéquation globale, surtout sur les "Maîtrises indispensables".
    - "resume_profil": Résumé global du profil.
    - "points_forts_cles": 2-3 points forts (techniques ou soft skills).
    - "points_faibles_risques": 1-2 risques (ex: manque d'expérience, techno manquante).
    - "adequation_poste": Une phrase simple (ex: "Bonne adéquation technique", "Mismatch sur les frameworks").
    - "evaluation_technologies_cles": **REQUIS.** Rédige 1-2 phrases évaluant le CV *uniquement* contre la stack indispensable (Laravel, Vue.js, NuxtJS, Tailwind). Si le candidat propose une alternative (ex: React), note-le ici.

    JSON ATTENDU (exemple):
    {{
      "score": 70,
      "resume_profil": "Développeur full-stack avec 2 ans d'expérience, compétent en PHP mais sans expérience directe sur Laravel ou Vue.js. Propose React comme alternative.",
      "points_forts_cles": ["Solide expérience PHP/SQL", "Maîtrise de React", "Autonome"],
      "points_faibles_risques": ["Mismatch sur les frameworks requis (Vue.js, Laravel)", "Anglais B1 (C1 requis)"],
      "adequation_poste": "Risque sur l'adéquation des frameworks JS/PHP.",
      "evaluation_technologies_cles": "Le candidat maîtrise PHP et SQL. Cependant, les requis indispensables Laravel, Vue.js et NuxtJS sont absents. Il mentionne React, une alternative à Vue.js."
    }}

    JSON:
    """
    response_str = None 
    try:
        response_str = call_openrouter_api(prompt, key_config, max_tokens=1000, temperature=0.2, force_json=True) # Augmenté max_tokens
        
        cleaned_json_string = response_str
        if response_str.startswith("```json"): cleaned_json_string = response_str[7:-3].strip()
        elif response_str.startswith("`"): cleaned_json_string = response_str.strip('`')

        try: data = json.loads(cleaned_json_string)
        except json.JSONDecodeError:
             logger.warning(f"Analyse Qualitative: tentative correction JSON...")
             corrected_json_string = cleaned_json_string.replace('\\_', '_').replace('\\*', '*')
             data = json.loads(corrected_json_string)

        # AJOUT DE LA NOUVELLE CLÉ REQUISE
        required_keys = ["score", "resume_profil", "points_forts_cles", "points_faibles_risques", "adequation_poste", "evaluation_technologies_cles"]
        if all(key in data for key in required_keys):
             try: 
                 score_val = int(data.get('score', 0))
                 data['score'] = max(0, min(score_val, 100))
             except: data['score'] = 0
             data['resume_profil'] = str(data.get('resume_profil', '')) 
             data['points_forts_cles'] = data.get('points_forts_cles', []) if isinstance(data.get('points_forts_cles'), list) else []
             data['points_faibles_risques'] = data.get('points_faibles_risques', []) if isinstance(data.get('points_faibles_risques'), list) else []
             data['adequation_poste'] = str(data.get('adequation_poste', ''))
             # PARSING DE LA NOUVELLE CLÉ
             data['evaluation_technologies_cles'] = str(data.get('evaluation_technologies_cles', ''))
             
             data['points_forts_cles'] = data['points_forts_cles'][:3]
             data['points_faibles_risques'] = data['points_faibles_risques'][:2]
             return data
        else:
            logger.warning(f"Analyse Qualitative JSON incomplet: Clés manquantes (dont 'evaluation_technologies_cles'?) dans {cleaned_json_string[:200]}...")
            return None
            
    except json.JSONDecodeError:
        logger.warning(f"Analyse Qualitative réponse non JSON (après nettoyage): {cleaned_json_string[:200]}...")
        return None
    except Exception as e:
        logger.error(f"Erreur appel/parsing Analyse Qualitative IA: {e}")
        return None

# --- ÉTAPE 4: Recherche Web (Locale) ---
@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=20), 
    stop=tenacity.stop_after_attempt(3),
    # Nous réessayons sur n'importe quelle Exception générique, 
    # car DDGS peut lever des erreurs variées (y compris non-HTTP) pour un ratelimit.
    retry=tenacity.retry_if_exception_type(Exception), 
    reraise=True
)
def perform_web_search(candidate_name, linkedin_url):
    """Effectue une recherche web simple et retourne les 3 premiers liens pertinents."""
    links = []
    if not candidate_name or "Basique)" in candidate_name or "Erreur" in candidate_name or "Manquant" in candidate_name:
        return links 

    query = f'"{candidate_name}"'
    if linkedin_url and 'linkedin.com' in linkedin_url:
        query += f' site:linkedin.com OR "{linkedin_url}"' 
    else:
        query += ' linkedin OR github OR portfolio OR blog' 

    st.write(f"🌐 Recherche web (simple) pour '{candidate_name}'...")
    try:
        # AJOUT D'UNE PAUSE de politesse de 1s avant l'appel
        time.sleep(1.0) 
        with DDGS(timeout=15) as ddgs:
            results = list(ddgs.text(query, max_results=7)) 
            
            seen_domains = set()
            for r in results:
                href = r.get('href')
                if href and 'duckduckgo.com' not in href and 'google.com' not in href and 'bing.com' not in href and 'wikipedia.org' not in href:
                    try:
                        domain = urlparse(href).netloc.replace('www.', '') 
                        is_social_coding = any(site in domain for site in ['linkedin.com', 'github.com', 'gitlab.com'])
                        
                        if is_social_coding or domain not in seen_domains:
                            links.append(href)
                            if not is_social_coding: seen_domains.add(domain)
                            if len(links) >= 3: break 
                    except Exception:
                        logger.warning(f"Impossible de parser l'URL de recherche: {href}")
                        
    except Exception as e:
        # L'erreur sera relancée par Tenacity si les 3 tentatives échouent
        st.warning(f"Recherche web échouée pour {candidate_name}: {e}")
        raise # Relance pour que Tenacity puisse l'attraper
    
    return links

# --- INTERFACE UTILISATEUR (UI) ---
# (Identique)
with st.sidebar:
    st.title("RH+ Pro")
    st.markdown("---")
    with st.expander("Mode d'emploi", expanded=True):
         st.info(
             """
             1.  **Collez** l'offre d'emploi complète.
             2.  **Chargez** vos CV (PDF).
             3.  **Cliquez** sur "Analyser les Candidatures".
             """
         )
    st.header("1. Description du Poste")
    job_description = st.text_area(
        label="Collez ici l'offre d'emploi complète", height=250,
        disabled=st.session_state.is_running,
        placeholder="Exemple : 'Recherche Développeur Python Junior...'"
    )
    st.header("2. CV des Candidats")
    uploaded_files = st.file_uploader(
        label="Chargez un ou plusieurs CV au format PDF", type="pdf",
        accept_multiple_files=True, disabled=st.session_state.is_running
    )

st.title("Synthèse de l'Analyse")
st.markdown("Optimisez votre présélection. Chargez plusieurs CV, analysez-les et identifiez les meilleurs talents.")
st.markdown("")
analyze_button = st.button(
    "Analyser les Candidatures", type="primary",
    use_container_width=True, disabled=st.session_state.is_running
)
st.markdown("---")

# --- LOGIQUE DE TRAITEMENT PRINCIPALE (Hybride V3 - CORRIGÉE) ---
if analyze_button:
    if not job_description.strip(): st.warning("Veuillez fournir une description de poste.")
    elif not uploaded_files: st.warning("Veuillez charger au moins un CV.")
    else:
        st.session_state.is_running = True
        st.session_state.all_results = []
        st.session_state.file_contents = {}
        st.session_state.analysis_done = True
        st.session_state.pop('api_provider_logged', None) 

        # --- POOL DE CLÉS API (OpenRouter UNIQUEMENT) ---
        api_keys_pool = []
        openrouter_model = "mistralai/mistral-7b-instruct:free" 
        # --- CORRECTION URL ---
        # Définir l'URL correctement SANS crochets
        openrouter_url = "https://openrouter.ai/api/v1/chat/completions" 
        # --- FIN CORRECTION ---
        if st.secrets.get("OPENROUTER_API_KEY"):
            api_keys_pool.append({"key": st.secrets.get("OPENROUTER_API_KEY"), "service": "openrouter", "model": openrouter_model, "url": openrouter_url})
        if st.secrets.get("OPENROUTER_API_KEY_2"):
             api_keys_pool.append({"key": st.secrets.get("OPENROUTER_API_KEY_2"), "service": "openrouter", "model": openrouter_model, "url": openrouter_url})
        if not api_keys_pool:
            st.error("❌ Aucune clé OpenRouter configurée dans st.secrets.")
            st.session_state.is_running = False
            st.stop()
        st.info(f"Pool de {len(api_keys_pool)} clés OpenRouter ({openrouter_model}).")
        # --- FIN POOL ---

        progress_bar = st.progress(0, text="Initialisation...")
        total_files = len(uploaded_files); start_time = time.time()
        stage_counts = {"extraction_ok": 0, "stage1_ok": 0, "stage2b_ok": 0, "stage3_ok": 0, "fallback_used": 0, "failed_total": 0}

        for i, uploaded_file in enumerate(uploaded_files):
            key_config_1 = api_keys_pool[i % len(api_keys_pool)] 
            key_config_2 = api_keys_pool[(i + 1) % len(api_keys_pool)] 

            filename = uploaded_file.name
            progress_text = f"Analyse {filename} ({i+1}/{total_files})..."
            progress_bar.progress((i + 1) / total_files, text=progress_text)

            # --- Initialize results dict ---
            final_result = {
                "nom_fichier": filename, "nom": "N/A", "score": 0, "resume_profil": "N/A",
                "contact": {}, "langues": [], "diplome_principal": "", "annees_experience_estimees": 0,
                "points_forts_cles": [], "points_faibles_risques": [], "adequation_poste": "",
                "evaluation_technologies_cles": "", # <- AJOUTER CETTE LIGNE
                "analyse_ats": {"mots_cles_trouves": [], "mots_cles_manquants": [], "stabilite": "N/A", "raffinement_ia": False},
                "web_links": [], "analysis_type": "Échec Initial"
            }

            # --- ÉTAPE 0: Extraction ---
            file_bytes = uploaded_file.getvalue()
            st.session_state.file_contents[filename] = file_bytes
            cv_text = extract_text_from_pdf(io.BytesIO(file_bytes), filename)

            if cv_text and len(cv_text) > 100: 
                stage_counts["extraction_ok"] += 1
                screening_data = None
                qualitative_data = None
                refined_keywords_data = None
                
                # --- ÉTAPE 1: Screening IA ---
                st.write(f"📄 {filename}: Étape 1 - Screening IA...")
                try:
                    screening_data = call_screening_ia(cv_text, job_description, key_config_1)
                    if screening_data:
                        final_result.update(screening_data) 
                        final_result["analysis_type"] = "IA Screening + Mots Clés Locaux" 
                        stage_counts["stage1_ok"] += 1
                    else:
                         logger.warning(f"Screening IA a retourné None pour {filename}.")
                         final_result["analysis_type"] = "Basique + Mots Clés Locaux" 
                         stage_counts["fallback_used"] += 1 
                # Catch specific retry error for better logging
                except tenacity.RetryError as e:
                     st.error(f"Screening IA échoué pour {filename} après {e.attempt_number} tentatives. Erreur finale: {e.last_attempt.exception()}", icon="🚨")
                     if isinstance(e.last_attempt.exception(), HTTPError) and e.last_attempt.exception().response.status_code == 429:
                          st.error("ERREUR 429 : LIMITE QUOTIDIENNE OpenRouter atteinte?", icon="⏳")
                     final_result["analysis_type"] = "Basique + Mots Clés Locaux"
                     stage_counts["fallback_used"] += 1
                except Exception as e:
                     st.error(f"Erreur inattendue Screening IA {filename}: {e}", icon="💥")
                     logger.exception(f"Traceback complet Screening IA {filename}:")
                     final_result["analysis_type"] = "Basique + Mots Clés Locaux"
                     stage_counts["fallback_used"] += 1
                     
                # Fallback pour nom/score/resume si screening échoue
                if not screening_data:
                     # ---- CORRECTION APPEL FALLBACK ----
                     # Appel de la fonction définie correctement
                     basic_fallback_data = get_basic_fallback_info(cv_text, job_description, filename) 
                     final_result["nom"] = basic_fallback_data["nom"]
                     final_result["score"] = basic_fallback_data["score"]
                     final_result["resume_profil"] = basic_fallback_data["resume_profil"] # Clé cohérente
                     # ---- FIN CORRECTION ----
                     
                # --- ÉTAPE 2: Analyse Mots Clés (Local + IA) ---
                st.write(f"📄 {filename}: Étape 2 - Mots Clés...")
                local_ats_analysis = perform_local_analysis(cv_text, job_description)
                mots_cles_trouves_bruts = local_ats_analysis.get("mots_cles_trouves", [])
                mots_cles_manquants_bruts = local_ats_analysis.get("mots_cles_manquants", [])
                
                refined_keywords_data = None
                if mots_cles_trouves_bruts or mots_cles_manquants_bruts:
                     try:
                          refined_keywords_data = call_keyword_refinement_ia(
                               mots_cles_trouves_bruts, mots_cles_manquants_bruts, 
                               cv_text, job_description, key_config_2 
                          )
                          if refined_keywords_data:
                               stage_counts["stage2b_ok"] += 1
                          else: logger.warning(f"Raffinement IA a retourné None pour {filename}.")
                     except tenacity.RetryError as e: st.error(f"Raffinement Mots-clés IA échoué {filename}: {e.last_attempt.exception()}", icon="🚨")
                     except Exception as e: st.error(f"Erreur inattendue Raffinement Mots-clés IA {filename}: {e}", icon="💥")

                # Update final_result["analyse_ats"]
                final_result["analyse_ats"]["stabilite"] = local_ats_analysis.get("stabilite", "N/A")
                if refined_keywords_data:
                    final_result["analyse_ats"]["mots_cles_trouves"] = refined_keywords_data.get("mots_cles_trouves_filtres", mots_cles_trouves_bruts)
                    final_result["analyse_ats"]["mots_cles_manquants"] = refined_keywords_data.get("mots_cles_manquants_prioritaires", mots_cles_manquants_bruts)
                    final_result["analyse_ats"]["raffinement_ia"] = True
                else:
                    final_result["analyse_ats"]["mots_cles_trouves"] = mots_cles_trouves_bruts
                    final_result["analyse_ats"]["mots_cles_manquants"] = mots_cles_manquants_bruts
                    final_result["analyse_ats"]["raffinement_ia"] = False

                # --- ÉTAPE 3: Analyse Qualitative IA ---
                if screening_data: # Attempt only if screening was successful
                     st.write(f"📄 {filename}: Étape 3 - Analyse Qualitative IA...")
                     try:
                          qualitative_data = call_qualitative_ia(cv_text, job_description, screening_data, key_config_1) 
                          if qualitative_data:
                               final_result.update(qualitative_data) 
                               final_result["analysis_type"] = "IA Complète" 
                               stage_counts["stage3_ok"] += 1
                          else:
                               logger.warning(f"Analyse Qualitative a retourné None pour {filename}.")
                               # If stage 3 fails, but stage 1 was ok, ensure score exists
                               if final_result.get("score", 0) == 0: 
                                    basic_fallback_score = get_basic_fallback_info(cv_text, job_description, filename)["score"]
                                    final_result["score"] = basic_fallback_score
                     except tenacity.RetryError as e: st.error(f"Analyse Qualitative IA échouée {filename}: {e.last_attempt.exception()}", icon="🚨")
                     except Exception as e: st.error(f"Erreur inattendue Analyse Qualitative IA {filename}: {e}", icon="💥")

                # --- ÉTAPE 4: Recherche Web ---
                st.write(f"📄 {filename}: Étape 4 - Recherche Web...")
                try:
                    linkedin_url = final_result.get("contact", {}).get("linkedin")
                    # Tenacity est déjà importé en haut de notre fichier
                    web_links = perform_web_search(final_result.get("nom"), linkedin_url)
                    final_result["web_links"] = web_links
                except tenacity.RetryError as e:
                    st.warning(f"Recherche Web pour {filename} échouée après {e.attempt_number} tentatives (Ratelimit de DDGS).", icon="🌐")
                    logger.warning(f"DDGS Ratelimit final pour {filename}: {e.last_attempt.exception()}")
                    final_result["web_links"] = [] # On continue avec une liste vide
                except Exception as e:
                    # Sécurité pour attraper d'autres erreurs inattendues de la recherche web
                    st.error(f"Erreur inattendue recherche Web {filename}: {e}", icon="💥")
                    logger.exception(f"Traceback complet recherche Web {filename}:")
                    final_result["web_links"] = [] # On continue avec une liste vide

            else: # PDF illisible ou trop court
                 error_msg = f"Impossible d'extraire assez de texte de {filename}."
                 if cv_text is not None: error_msg += f" ({len(cv_text)} car.). Analyse impossible."
                 else: error_msg += " Fichier illisible."
                 st.error(error_msg)
                 final_result.update({
                      "nom": "Erreur Extraction", "score": 0, "resume_profil": error_msg,
                      "analyse_ats": {}, "analysis_type": "Échec Extraction"
                 })
                 stage_counts["failed_total"] += 1 
            
            # Ensure essential keys exist
            final_result.setdefault("nom", "Erreur Inconnue")
            final_result.setdefault("score", 0)
            final_result.setdefault("resume_profil", "N/A") 
            final_result.setdefault("analyse_ats", {"mots_cles_trouves": [], "mots_cles_manquants": [], "stabilite": "N/A", "raffinement_ia": False})
            final_result.setdefault("analysis_type", "Échec")

            st.session_state.all_results.append(final_result)
                 
            # --- PAUSE ENTRE CVs ---
            time.sleep(3.0) 

        # --- Finalisation & Reporting ---
        progress_bar.empty(); st.session_state.is_running = False
        total_time = time.time() - start_time
        api_used_log = st.session_state.get('api_provider_logged', 'Aucun appel IA réussi')
        st.info(f"Analyse terminée en {total_time:.1f}s. (API utilisée: {api_used_log})")
        
        st.write("---")
        st.subheader("Résumé du Traitement :")
        cols = st.columns(3)
        cols[0].metric("CV Lus", f"{stage_counts['extraction_ok']}/{total_files}")
        cols[1].metric("Screening IA OK", f"{stage_counts['stage1_ok']}/{stage_counts['extraction_ok']}")
        cols[2].metric("Analyse Quali. IA OK", f"{stage_counts['stage3_ok']}/{stage_counts['stage1_ok']}") 
        
        final_ia_complete = sum(1 for r in st.session_state.all_results if r['analysis_type'] == "IA Complète")
        final_ia_screening = sum(1 for r in st.session_state.all_results if r['analysis_type'] == "IA Screening + Mots Clés Locaux")
        final_basic = sum(1 for r in st.session_state.all_results if r['analysis_type'] == "Basique + Mots Clés Locaux")
        final_failed = total_files - final_ia_complete - final_ia_screening - final_basic

        if final_ia_complete > 0: st.success(f"{final_ia_complete} CV avec analyse IA complète.")
        if final_ia_screening > 0: st.info(f"{final_ia_screening} CV avec screening IA + analyse locale.")
        if final_basic > 0: st.warning(f"{final_basic} CV avec fallback basique + analyse locale.")
        if final_failed > 0: st.error(f"{final_failed} CV non analysés (extraction échouée).")


# --- AFFICHAGE DES RÉSULTATS (Adapté au Workflow V3 + CORRECTION UI ATS) ---
if st.session_state.analysis_done and st.session_state.all_results:
    sorted_results = sorted(st.session_state.all_results, key=lambda x: x.get('score', 0), reverse=True)

    try: # Export CSV
        df = pd.DataFrame(st.session_state.all_results)
        if not df.empty:
            if 'analyse_ats' in df.columns:
                 df['analyse_ats'] = df['analyse_ats'].apply(lambda x: x if isinstance(x, dict) else {})
                 df['ats.mots_cles_trouves'] = df['analyse_ats'].apply(lambda x: "; ".join(x.get('mots_cles_trouves', [])))
                 df['ats.mots_cles_manquants'] = df['analyse_ats'].apply(lambda x: "; ".join(x.get('mots_cles_manquants', [])))
                 df['ats.stabilite'] = df['analyse_ats'].apply(lambda x: x.get('stabilite', 'N/A'))
                 df['ats.raffinement_ia'] = df['analyse_ats'].apply(lambda x: x.get('raffinement_ia', False))
                 if 'analyse_ats' in df.columns: df = df.drop(columns=['analyse_ats'])
            if 'contact' in df.columns:
                 df['contact'] = df['contact'].apply(lambda x: x if isinstance(x, dict) else {})
                 df['contact.email'] = df['contact'].apply(lambda x: x.get('email', ''))
                 df['contact.telephone'] = df['contact'].apply(lambda x: x.get('telephone', ''))
                 df['contact.linkedin'] = df['contact'].apply(lambda x: x.get('linkedin', ''))
                 if 'contact' in df.columns: df = df.drop(columns=['contact'])
            for col in ["langues", "points_forts_cles", "points_faibles_risques", "web_links"]:
                 if col in df.columns: df[col] = df[col].apply(lambda x: "; ".join(map(str, x)) if isinstance(x, list) else str(x))

            csv_data = convert_df_to_csv(df.fillna('N/A'))
            if csv_data:
                st.download_button(label="Exporter Résultats (CSV)", data=csv_data,
                                   file_name=f"analyse_cv_v3_{time.strftime('%Y%m%d_%H%M')}.csv",
                                   mime='text/csv', use_container_width=True)
            st.markdown("---")
    except Exception as e: st.error(f"Erreur Export CSV : {e}")

    st.subheader(f"Classement des {len(sorted_results)} Profils Analysés")
    for i, candidate in enumerate(sorted_results):
        score = candidate.get('score', 0)
        nom = candidate.get('nom', 'N/A')
        nom_fichier = candidate.get('nom_fichier', 'N/A')
        analysis_type = candidate.get('analysis_type', 'Échec')
        resume = candidate.get('resume_profil', 'N/A') 
        contact = candidate.get('contact', {})
        langues = candidate.get('langues', [])
        diplome = candidate.get('diplome_principal', '')
        exp = candidate.get('annees_experience_estimees', 0)
        points_forts = candidate.get('points_forts_cles', [])
        points_faibles = candidate.get('points_faibles_risques', [])
        adequation = candidate.get('adequation_poste', '')
        eval_tech = candidate.get('evaluation_technologies_cles', '')
        ats_data = candidate.get('analyse_ats', {})
        web_links = candidate.get('web_links', [])

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"### {i+1}. {nom} ({nom_fichier})")
                
                if analysis_type == "IA Complète": st.caption("Analyse : IA Complète ✨")
                elif analysis_type == "IA Screening + Mots Clés Locaux": st.caption("Analyse : IA Screening + Mots Clés Locaux 🧐")
                elif analysis_type == "Basique + Mots Clés Locaux": st.caption("Analyse : Basique Fallback + Mots Clés Locaux ⚠️")
                else: st.caption(f"Analyse : {analysis_type} ❌") 

                contact_parts = []
                if contact.get('email'): contact_parts.append(f"📧 [{contact['email']}](mailto:{contact['email']})")
                if contact.get('telephone'): contact_parts.append(f"📞 {contact['telephone']}")
                if contact.get('linkedin'): contact_parts.append(f"🔗 [LinkedIn]({contact['linkedin']})")
                if contact_parts: st.markdown(" | ".join(contact_parts))

                info_line = []
                if langues: info_line.append(f"🗣️ {', '.join(langues)}")
                if diplome: info_line.append(f"🎓 {diplome}")
                if exp > 0: info_line.append(f"⏳ {exp} an(s) exp.")
                if info_line: st.markdown(" | ".join(info_line))

                st.markdown(f"**Résumé :** *{resume}*")

            with col2:
                st.metric(label="Score", value=f"{score}%")
                if nom_fichier in st.session_state.file_contents:
                     st.download_button(label="Télécharger CV", data=st.session_state.file_contents[nom_fichier],
                                        file_name=nom_fichier, mime="application/pdf", key=f"btn_{nom_fichier}_{i}")

            if analysis_type not in ["Échec Extraction", "Échec", "Échec Initial"]: # Show details only if some analysis happened
                st.markdown("---")
                
                tabs_list = ["📊 Analyse ATS"] 
                if analysis_type == "IA Complète":
                     tabs_list.insert(0, "🧑‍💼 Avis Qualitatif") 
                if web_links:
                     tabs_list.append("🌐 Liens Web")
                     
                tabs = st.tabs(tabs_list)
                tab_index = 0

                if "🧑‍💼 Avis Qualitatif" in tabs_list:
                    with tabs[tab_index]:
                        st.subheader("Avis Qualitatif (IA)")
                        if adequation: st.markdown(f"**Adéquation au poste :** {adequation}")
                        if eval_tech:
                            st.markdown(f"**Évaluation Technologies Clés :**")
                            st.info(f"{eval_tech}", icon="💻")
                        st.markdown("**Points Forts Clés :**")
                        if points_forts: 
                            for p in points_forts: st.markdown(f"- {p}") # Boucle correcte
                        else: st.info("-")
                        st.markdown("**Points Faibles / Risques :**")
                        if points_faibles: 
                            for p in points_faibles: st.warning(p, icon="🚩") # Boucle correcte
                        else: st.info("-")
                    tab_index += 1

                # ATS Tab 
                with tabs[tab_index]:
                    st.subheader("Analyse Technique (Mots Clés)")
                    raffinement_ok = ats_data.get('raffinement_ia', False)
                    if raffinement_ok: st.caption("Mots-clés filtrés par IA ✨")
                    else: st.caption("Mots-clés bruts/locaux ⚠️")
                        
                    col_ats1, col_ats2 = st.columns(2)
                    with col_ats1:
                        st.markdown("**Mots-clés trouvés :**")
                        mkt = ats_data.get('mots_cles_trouves', [])
                        # --- CORRECTION UI ATS ---
                        # Afficher la liste directement si elle existe
                        if mkt: st.success(f"{', '.join(mkt)}", icon="✅")
                        else: st.info("-")
                        # --- FIN CORRECTION ---
                        st.markdown("**Stabilité (Estimation) :**")
                        st.info(f"{ats_data.get('stabilite', 'N/A')}", icon="⏳")
                    with col_ats2:
                        st.markdown("**Mots-clés manquants :**")
                        mkm = ats_data.get('mots_cles_manquants', [])
                        # --- CORRECTION UI ATS ---
                        # Afficher la liste directement si elle existe
                        if mkm: st.error(f"{', '.join(mkm)}", icon="❌")
                        else: st.info("-")
                        # --- FIN CORRECTION ---
                tab_index += 1
                
                if "🌐 Liens Web" in tabs_list:
                     with tabs[tab_index]:
                         st.subheader("Présence en Ligne (Liens trouvés)")
                         if web_links:
                              for link in web_links: st.markdown(f"- [{link}]({link})")
                         else:
                              st.info("Aucun lien pertinent trouvé.")
                     tab_index += 1


elif not st.session_state.is_running and st.session_state.analysis_done and not st.session_state.all_results:
    st.error("L'analyse a terminé, mais aucun CV n'a pu être traité.")
elif not st.session_state.is_running:
    st.info("Prêt à analyser. Remplissez l'offre et chargez les CV.")