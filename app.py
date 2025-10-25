import streamlit as st
import streamlit.components.v1 as components
import os

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="RH+ Pro | L'IA qui analyse les CV pour vous.",
    page_icon="📄",
    layout="wide"
)

# --- CACHER LES ÉLÉMENTS STREAMLIT PAR DÉFAUT ---
# (La sidebar, le padding en haut, etc.)
st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        /* Corrige la marge blanche en haut de la page */
        .main .block-container {
            padding-top: 0rem;
            padding-bottom: 0rem;
            margin-top: 0rem;
        }
        /* Cache le header "Made with Streamlit" */
        header {
            visibility: hidden;
        }
        /* Cache le footer "Made with Streamlit" */
        footer {
            visibility: hidden;
        }
        /* Cache le menu hamburger */
        [data-testid="stActionButton"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- FONCTION POUR LIRE LES FICHIERS ---
def read_file_content(file_path):
    """Ouvre et lit un fichier, retourne son contenu."""
    try:
        # S'assure qu'on part du bon dossier (le dossier du script)
        script_dir = os.path.dirname(__file__)
        full_path = os.path.join(script_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Erreur Critique : Le fichier '{file_path}' est introuvable.")
        st.info(f"Assure-toi que '{file_path}' est dans le même dossier que 'app.py'.")
        return ""
    except Exception as e:
        st.error(f"Erreur inattendue en lisant {file_path}: {e}")
        return ""

# --- 1. Lire le CSS ---
css_content = read_file_content("style.css")

# --- 2. Lire le HTML ---
html_content = read_file_content("index.html")

if css_content and html_content:
    # --- 3. Injecter le CSS dans le HTML ---
    # On remplace le <link> par le contenu réel du CSS pour
    # que le composant HTML ait tout ce dont il a besoin.
    final_html = html_content.replace(
        '<link rel="stylesheet" href="style.css">', 
        f"<style>{css_content}</style>"
    )
    
    # --- 4. Afficher la page complète ---
    # C'est la fonction correcte pour afficher une page HTML
    # On met une hauteur très grande pour que le scrolling soit géré par le HTML
    components.html(final_html, height=4000, scrolling=True)
else:
    st.error("L'application n'a pas pu démarrer.")
    st.info("Vérifie que 'index.html' et 'style.css' sont présents.")