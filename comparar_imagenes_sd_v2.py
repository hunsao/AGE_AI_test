import streamlit as st
from PIL import Image
import os

# Función para obtener los metadatos de una imagen PNG
def get_png_metadata(image_path):
    image = Image.open(image_path)
    image.load()  # Cargar la imagen para asegurar que se lean los metadatos PNG
    return image.info

# Función para leer las imágenes de una carpeta
def read_images_from_folder(folder_path):
    images = {}
    for filename in os.listdir(folder_path):
        if filename.endswith(".png"):
            image_path = os.path.join(folder_path, filename)
            images[filename] = image_path
    return images

# Función para formatear los metadatos
def format_metadata(metadata):
    formatted_metadata = {}
    for item in metadata.split('\n'):
        if item.strip():
            parts = item.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""
            formatted_metadata[key] = value
    return formatted_metadata

# Interfaz para ingresar manualmente las rutas de las carpetas
st.title("AGEAI: Imágenes / Metadatos PNG")

st.markdown("----")

folder1 = st.text_input("Ruta de la carpeta NEUTRAL")
folder2 = st.text_input("Ruta de la carpeta OLDER")

st.markdown("----")

if folder1 and folder2:
    if os.path.isdir(folder1) and os.path.isdir(folder2):
        # Leer las imágenes de las carpetas ingresadas
        images1 = read_images_from_folder(folder1)
        images2 = read_images_from_folder(folder2)

        # Filtrar imágenes que tienen los mismos nombres en ambas carpetas
        common_images = set(images1.keys()).intersection(set(images2.keys()))

        for image_name in sorted(common_images):
            image1_path = images1[image_name]
            image2_path = images2[image_name]

            col1, col2 = st.columns(2)

            with col1:
                #st.header("NEUTRAL")
                st.image(image1_path, caption=image_name)
                metadata1 = get_png_metadata(image1_path)
                formatted_metadata1 = format_metadata(metadata1.get('parameters', ''))
                for key, value in formatted_metadata1.items():
                    st.write(f"**{key}**: {value}")

            with col2:
                #st.header("OLDER")
                st.image(image2_path, caption=image_name)
                metadata2 = get_png_metadata(image2_path)
                formatted_metadata2 = format_metadata(metadata2.get('parameters', ''))
                for key, value in formatted_metadata2.items():
                    st.write(f"**{key}**: {value}")
    else:
        st.warning("Por favor, asegúrate de ingresar rutas válidas de carpetas.")

#streamlit run c:/Users/David/Documents/AGEAI/Scripts/comparar_imagenes_sd_v2.py