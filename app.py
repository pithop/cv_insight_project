import streamlit as st
import os

# --- CONFIGURATION DE LA PAGE (TRÈS IMPORTANT) ---
st.set_page_config(
    page_title="RH+ Pro | L'IA qui analyse les CV pour vous.",
    page_icon="📄",
    layout="wide" # La landing page doit prendre toute la largeur
)

# --- CACHER LA SIDEBAR DE STREAMLIT SUR LA LANDING PAGE ---
# On la cache ici, mais elle sera visible sur la page "Demo"
st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- FONCTION POUR LIRE LES FICHIERS CSS ET HTML ---
def read_file_content(file_path):
    """Ouvre et lit un fichier, retourne son contenu."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Erreur : Le fichier {file_path} est introuvable.")
        st.error(f"Répertoire actuel : {os.getcwd()}")
        return ""
    except Exception as e:
        st.error(f"Erreur inattendue en lisant {file_path}: {e}")
        return ""

# --- INJECTER LE CSS ---
css_content = read_file_content("style.css")
if css_content:
    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

# --- INJECTER LE HTML ---
html_content = read_file_content("index.html")
if html_content:
    # On utilise st.markdown pour "servir" le HTML
    st.markdown(html_content, unsafe_allow_html=True)