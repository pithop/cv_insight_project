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
        header { visibility: hidden; }
        footer { visibility: hidden; }
        [data-testid="stActionButton"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True
)

# --- FONCTION POUR LIRE LES FICHIERS ---
def read_file_content(file_path):
    """Ouvre et lit un fichier, retourne son contenu."""
    try:
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
    final_html = html_content.replace(
        '<link rel="stylesheet" href="style.css">', 
        f"<style>{css_content}</style>"
    )
    
    # --- 4. CORRECTION : AJOUTER UN SCRIPT POUR L'AUTO-HAUTEUR ---
    # Ce script envoie un message à Streamlit avec la hauteur
    # réelle de la page, pour que l'iframe s'adapte.
    auto_height_script = """
    <script>
        // Fonction pour envoyer la hauteur à Streamlit
        const sendHeight = () => {
            const height = document.documentElement.scrollHeight;
            window.parent.postMessage({
                isStreamlitMessage: true, // Nécessaire pour que Streamlit écoute
                type: 'setFrameHeight',
                height: height
            }, '*');
        };

        // Envoyer au chargement initial
        window.addEventListener('load', sendHeight);

        // Envoyer lors du redimensionnement
        window.addEventListener('resize', sendHeight);

        // Observer les changements dans le DOM (ex: animations)
        const observer = new MutationObserver(sendHeight);
        observer.observe(document.body, {
            attributes: true,
            childList: true,
            subtree: true
        });

        // Envoyer la hauteur à intervalles réguliers (pour l'animation)
        setInterval(sendHeight, 500);
    </script>
    """
    
    # On ajoute le script juste avant la fin du </body>
    final_html = final_html.replace("</body>", f"{auto_height_script}</body>")
    
    # --- 5. Afficher la page complète (CORRECTION) ---
    # On enlève la hauteur fixe.
    # scrolling=False est important pour que la page principale défile,
    # et non l'iframe.
    components.html(final_html, scrolling=False)

else:
    st.error("L'application n'a pas pu démarrer.")
    st.info("Vérifie que 'index.html' et 'style.css' sont présents.")