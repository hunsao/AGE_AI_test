import streamlit as st
from zipfile import ZipFile
import os
import shutil
from PIL import Image
import re
import pandas as pd
import io
from st_aggrid import AgGrid

# Function to extract a ZIP file
def extract_zip(zip_path, extract_to):
    with ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def show_image_details(image_data):
    for key, value in image_data.items():
        st.write(f"**{key}:** {value}")

# Function to read images from a folder and sort them naturally
def read_images_from_folder(folder_path):
    images = {}
    filenames = sorted(os.listdir(folder_path), key=natural_sort_key)
    for filename in filenames:
        if filename.endswith(".jpg"):
            image_path = os.path.join(folder_path, filename)
            images[filename] = image_path
    return images

# Natural sort function
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def read_dataframe_from_zip(zip_path):
    with ZipFile(zip_path, 'r') as zip_ref:
        if 'df_results.csv' in zip_ref.namelist():
            with zip_ref.open('df_results.csv') as csv_file:
                return pd.read_csv(io.BytesIO(csv_file.read()))
    return None

# Streamlit interface for uploading a ZIP file and extracting folders
st.set_page_config(layout="wide")

st.markdown("<h1 style='text-align: center; color: white;'>AGEAI: Imágenes y Metadatos</h1>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Sube un archivo ZIP que contenga las carpetas NEUTRAL, OLDER y el csv:", type="zip")

if uploaded_file:
    # Save the uploaded ZIP file to a temporary location
    temp_zip_path = "temp.zip"
    with open(temp_zip_path, 'wb') as f:
        f.write(uploaded_file.read())

    # Extract the content of the ZIP file
    temp_extract_path = "extracted_folders"
    extract_zip(temp_zip_path, temp_extract_path)

    # Search for NEUTRAL and OLDER folders within the extracted folder
    folders = os.listdir(temp_extract_path)
    if 'NEUTRAL' in folders and 'OLDER' in folders:
        folder1 = os.path.join(temp_extract_path, 'NEUTRAL')
        folder2 = os.path.join(temp_extract_path, 'OLDER')

        # Read images from the selected folders and sort them naturally
        images1 = read_images_from_folder(folder1)
        images2 = read_images_from_folder(folder2)

        # Read the DataFrame from the ZIP file
        df_results = read_dataframe_from_zip(temp_zip_path)
        if df_results is not None:
            # Clean DataFrame: Drop rows with NaN in critical columns
            df_results = df_results.dropna(subset=['ID', 'ID_jpg', 'Prompt'])

            # Mostrar el DataFrame completo
            st.subheader("Base de dades")
            AgGrid(df_results, height=600, width='100%', fit_columns_on_grid_load=True, enable_enterprise_modules=False)

            st.divider()

            # Buscador de variables en la barra lateral
            st.sidebar.header("Buscador de Variables")
            search_columns = df_results.columns.tolist()
            selected_column = st.sidebar.selectbox("Seleccionar Variable para Buscar", search_columns)
            search_term = st.sidebar.text_input(f"Buscar en {selected_column}")

            # Filtros existentes
            st.sidebar.header("Filtrar Imágenes")
            group_filter = st.sidebar.selectbox("Seleccionar Grupo", ["Todos", "NEUTRAL", "OLDER"], index=0)

            # Categorías para filtros
            categories = {
                "shoot": ["full shot", "close-up shot"],
                "role_gender": ["woman", "man", "person"],
                "activities": ["walking", "eating", "dressing", "taking a shower", "get pissed", "toileting", "ordering a taxi", "paying bills", "shopping", "doing home chores",
                            "using the phone", "at home", "in the living room", "in a room", "in winter"],
                "emotions_short": ["neutral", "positive", "negative"],
                "personality_short": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
                "location": ["indoors", "outdoors"]
            }

            # Filtros por categorías
            selected_shoot = st.sidebar.multiselect("Seleccionar Shoot", categories["shoot"], default=categories["shoot"])
            selected_role_gender = st.sidebar.multiselect("Seleccionar Role/Gender", categories["role_gender"], default=categories["role_gender"])
            selected_activities = st.sidebar.multiselect("Seleccionar Activities", categories["activities"], default=categories["activities"])
            selected_emotions = st.sidebar.multiselect("Seleccionar Emotions", categories["emotions_short"], default=categories["emotions_short"])
            selected_personality = st.sidebar.multiselect("Seleccionar Personality", categories["personality_short"], default=categories["personality_short"])
            selected_location = st.sidebar.multiselect("Seleccionar Location", categories["location"], default=categories["location"])

            # Filtro por rango de edad
            age_ranges = sorted(df_results['age_range'].unique().tolist())
            selected_age_ranges = st.sidebar.multiselect("Seleccionar Age Range", age_ranges, default=age_ranges)

            # Aplicar filtros al DataFrame
            filtered_df = df_results.copy()

            # Aplicar filtro de grupo
            if group_filter == "NEUTRAL":
                filtered_df = filtered_df[filtered_df['ID'].str.startswith('a_')]
            elif group_filter == "OLDER":
                filtered_df = filtered_df[filtered_df['ID'].str.startswith('o_')]

            # Aplicar filtros de categorías
            if 'Prompt' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item in x for item in selected_shoot))]
                filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item in x for item in selected_role_gender))]
                filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item in x for item in selected_activities))]
            else:
                st.error("La columna 'Prompt' no se encuentra en el DataFrame.")
                st.stop()

            # Aplicar nuevos filtros
            filtered_df = filtered_df[filtered_df['emotions_short'].isin(selected_emotions)]
            filtered_df = filtered_df[filtered_df['personality_short'].isin(selected_personality)]
            filtered_df = filtered_df[filtered_df['location'].isin(selected_location)]
            filtered_df = filtered_df[filtered_df['age_range'].isin(selected_age_ranges)]

            # Aplicar el filtro de búsqueda
            if search_term:
                filtered_df = filtered_df[filtered_df[selected_column].astype(str).str.contains(search_term, case=False, na=False)]

            # Mostrar imágenes basadas en el DataFrame filtrado
            st.subheader("Imágenes Filtradas")
            for i in range(0, len(filtered_df), 4):  # 4 imágenes por fila
                row_data = filtered_df.iloc[i:i+4]
                cols = st.columns(len(row_data))  # Cada imagen tiene una columna

                for col_index, (_, row) in enumerate(row_data.iterrows()):
                    image_name = row['ID_jpg']
                    if isinstance(image_name, str):
                        if image_name.startswith('a_') and image_name in images1:
                            cols[col_index].image(images1[image_name], caption=image_name, use_column_width=True)
                            with cols[col_index].expander("Ver detalles", expanded=False):
                                show_image_details(row.to_dict())
                        elif image_name.startswith('o_') and image_name in images2:
                            cols[col_index].image(images2[image_name], caption=image_name, use_column_width=True)
                            with cols[col_index].expander("Ver detalles", expanded=False):
                                show_image_details(row.to_dict())

                # Añadir línea horizontal después de cada fila de imágenes
                st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

        else:
            st.error("No se encontró el archivo df_results.csv en el ZIP.")

    else:
        st.error("No se encontraron las carpetas NEUTRAL y OLDER en el archivo ZIP.")

    # Remove temporary files and folders
    os.remove(temp_zip_path)
    shutil.rmtree(temp_extract_path, ignore_errors=True)