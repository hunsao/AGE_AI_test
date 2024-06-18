import streamlit as st
from zipfile import ZipFile
import os
import shutil

# Función para obtener los metadatos de una imagen PNG
def get_png_metadata(image_path):
    try:
        from PIL import Image
        image = Image.open(image_path)
        image.load()  # Cargar la imagen para asegurar que se lean los metadatos PNG
        return image.info
    except ImportError:
        return {}

# Función para extraer un archivo ZIP
def extract_zip(zip_path, extract_to):
    with ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

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

# Interfaz para cargar un archivo ZIP y extraer las carpetas
st.title("Comparación de Imágenes y Metadatos PNG")

uploaded_file = st.file_uploader("Sube un archivo ZIP que contenga las carpetas NEUTRAL y OLDER", type="zip")

if uploaded_file:
    # Guardar el archivo ZIP en una ubicación temporal
    temp_zip_path = "temp.zip"
    with open(temp_zip_path, 'wb') as f:
        f.write(uploaded_file.read())

    # Extraer el contenido del archivo ZIP
    temp_extract_path = "extracted_folders"
    extract_zip(temp_zip_path, temp_extract_path)

    # Buscar las carpetas NEUTRAL y OLDER dentro de la carpeta extraída
    folders = os.listdir(temp_extract_path)
    if 'NEUTRAL' in folders and 'OLDER' in folders:
        folder1 = os.path.join(temp_extract_path, 'NEUTRAL')
        folder2 = os.path.join(temp_extract_path, 'OLDER')

        # Leer las imágenes de las carpetas seleccionadas
        images1 = read_images_from_folder(folder1)
        images2 = read_images_from_folder(folder2)

        # Filtrar imágenes que tienen los mismos nombres en ambas carpetas
        common_images = set(images1.keys()).intersection(set(images2.keys()))

        for image_name in sorted(common_images):
            image1_path = images1[image_name]
            image2_path = images2[image_name]

            col1, col2 = st.columns(2)

            with col1:
                st.header("NEUTRAL")
                st.image(image1_path, caption=image_name)
                metadata1 = get_png_metadata(image1_path)
                formatted_metadata1 = format_metadata(metadata1.get('parameters', ''))
                for key, value in formatted_metadata1.items():
                    st.write(f"**{key}**: {value}")

            with col2:
                st.header("OLDER")
                st.image(image2_path, caption=image_name)
                metadata2 = get_png_metadata(image2_path)
                formatted_metadata2 = format_metadata(metadata2.get('parameters', ''))
                for key, value in formatted_metadata2.items():
                    st.write(f"**{key}**: {value}")

    else:
        st.warning("No se encontraron las carpetas NEUTRAL y OLDER dentro del archivo ZIP.")

    # Eliminar los archivos y carpetas temporales
    os.remove(temp_zip_path)
    shutil.rmtree(temp_extract_path, ignore_errors=True)


#streamlit run c:/Users/David/Documents/AGEAI/Scripts/comparar_imagenes_sd_v2.py