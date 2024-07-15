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

def create_downloadable_zip(filtered_df, images1, images2):
    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, 'w') as zip_file:
        for _, row in filtered_df.iterrows():
            image_name = row['ID_jpg']
            if isinstance(image_name, str):
                if image_name.startswith('a_') and image_name in images1:
                    image_path = images1[image_name]
                elif image_name.startswith('o_') and image_name in images2:
                    image_path = images2[image_name]
                else:
                    continue
                zip_file.write(image_path, image_name)
    
    zip_buffer.seek(0)
    return zip_buffer

def toggle_fullscreen(image_name):
    if st.session_state.fullscreen_image == image_name:
        st.session_state.fullscreen_image = None
    else:
        st.session_state.fullscreen_image = image_name

def get_default(category):
    if category in st.session_state:
        return st.session_state[category]
    return []

if 'fullscreen_image' not in st.session_state:
    st.session_state.fullscreen_image = None

#############################################################################################################################

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

    folders = os.listdir(temp_extract_path)

    if 'NEUTRAL' in folders and 'OLDER' in folders:
        folder1 = os.path.join(temp_extract_path, 'NEUTRAL')
        folder2 = os.path.join(temp_extract_path, 'OLDER')

        images1 = read_images_from_folder(folder1)
        images2 = read_images_from_folder(folder2)

        df_results = read_dataframe_from_zip(temp_zip_path)
        if df_results is not None:
            df_results = df_results.dropna(subset=['ID', 'ID_jpg', 'Prompt'])
            df_results['gender'] = df_results['Prompt'].apply(lambda x: 'woman' if 'woman' in x.lower().split() else ('man' if 'man' in x.lower().split() else 'person'))

            st.sidebar.header("Filtrar Imágenes")
            group_filter = st.sidebar.selectbox("Seleccionar Grupo", ["Todos", "NEUTRAL", "OLDER"], index=0)

            categories = {
                "shoot": ["full shot", "close-up shot"],
                "gender": ["woman", "man", "person"],
                "activities": ["walking", "eating", "dressing", "taking a shower", "get pissed", "toileting", "ordering a taxi", "paying bills", "shopping", "doing home chores",
                            "using the phone", "at home", "in the living room", "in a room", "in winter"],
                "emotions_short": ["neutral", "positive", "negative"],
                "personality_short": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
                "location": ["indoors", "outdoors"]
            }

            if 'reset_filters' not in st.session_state:
                st.session_state.reset_filters = False

            if st.sidebar.button("Resetear Filtros"):
                st.session_state.reset_filters = True
                for key in st.session_state.keys():
                    if key.startswith('multiselect_'):
                        st.session_state[key] = []

            # Function to get default values for multiselect widgets
            def get_default(category):
                if st.session_state.reset_filters:
                    return []
                return st.session_state.get(f"multiselect_{category}", [])

            # Define multiselect widgets with the updated get_default function
            selected_shoot = st.sidebar.multiselect("Seleccionar Shoot", categories["shoot"], default=get_default("shoot"), key="multiselect_shoot")
            selected_gender = st.sidebar.multiselect("Seleccionar Gender", categories["gender"], default=get_default("gender"), key="multiselect_gender")
            selected_activities = st.sidebar.multiselect("Seleccionar Activities", categories["activities"], default=get_default("activities"), key="multiselect_activities")
            selected_emotions = st.sidebar.multiselect("Seleccionar Emotions", categories["emotions_short"], default=get_default("emotions"), key="multiselect_emotions")
            selected_personality = st.sidebar.multiselect("Seleccionar Personality", categories["personality_short"], default=get_default("personality"), key="multiselect_personality")
            selected_location = st.sidebar.multiselect("Seleccionar Location", categories["location"], default=get_default("location"), key="multiselect_location")

            age_ranges = sorted(df_results['age_range'].unique().tolist())
            selected_age_ranges = st.sidebar.multiselect("Seleccionar Age Range", age_ranges, default=get_default("age_ranges"), key="multiselect_age_ranges")

            # Reset the flag after all widgets have been rendered
            if st.session_state.reset_filters:
                st.session_state.reset_filters = False


            st.sidebar.header("Buscador de Variables")
            search_columns = df_results.columns.tolist()
            selected_column = st.sidebar.selectbox("Seleccionar Variable para Buscar", search_columns)
            search_term = st.sidebar.text_input(f"Buscar en {selected_column}")

            filtered_df = df_results.copy()

            if group_filter == "NEUTRAL":
                filtered_df = filtered_df[filtered_df['ID'].str.startswith('a_')]
            elif group_filter == "OLDER":
                filtered_df = filtered_df[filtered_df['ID'].str.startswith('o_')]

            if 'Prompt' in filtered_df.columns:
                if selected_shoot:
                    filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item in x for item in selected_shoot))]
                if selected_gender:
                    filtered_df = filtered_df[filtered_df['gender'].isin(selected_gender)]
                if selected_activities:
                    filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item in x for item in selected_activities))]
            else:
                st.error("La columna 'Prompt' no se encuentra en el DataFrame.")
                st.stop()

            if selected_emotions:
                filtered_df = filtered_df[filtered_df['emotions_short'].isin(selected_emotions)]
            if selected_personality:
                filtered_df = filtered_df[filtered_df['personality_short'].isin(selected_personality)]
            if selected_location:
                filtered_df = filtered_df[filtered_df['location'].isin(selected_location)]
            if selected_age_ranges:
                filtered_df = filtered_df[filtered_df['age_range'].isin(selected_age_ranges)]

            if search_term:
                filtered_df = filtered_df[filtered_df[selected_column].astype(str).str.contains(search_term, case=False, na=False)]

            #st.subheader("Base de datos")
            AgGrid(filtered_df, height=600, width='100%', fit_columns_on_grid_load=True, enable_enterprise_modules=False)

            # Botón para descargar el DataFrame filtrado
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="Descargar DataFrame Filtrado",
                data=csv,
                file_name="filtered_dataframe.csv",
                mime="text/csv",
            )

            st.divider()

            # Mostrar información sobre las imágenes filtradas y los filtros aplicados
            #st.subheader("Imágenes Filtradas")
            st.write(f"Número de imágenes filtradas: {len(filtered_df)}")
            
            applied_filters = []
            if group_filter != "Todos":
                applied_filters.append(f"Grupo: {group_filter}")
            if selected_shoot:
                applied_filters.append(f"Shoot: {', '.join(selected_shoot)}")
            if selected_gender:
                applied_filters.append(f"Gender: {', '.join(selected_gender)}")
            if selected_activities:
                applied_filters.append(f"Activities: {', '.join(selected_activities)}")
            if selected_emotions:
                applied_filters.append(f"Emotions: {', '.join(selected_emotions)}")
            if selected_personality:
                applied_filters.append(f"Personality: {', '.join(selected_personality)}")
            if selected_location:
                applied_filters.append(f"Location: {', '.join(selected_location)}")
            if selected_age_ranges:
                applied_filters.append(f"Age Range: {', '.join(map(str, selected_age_ranges))}")
            if search_term:
                applied_filters.append(f"Búsqueda: '{search_term}' en '{selected_column}'")

            if applied_filters:
                st.write("Filtros aplicados:")
                for filter_info in applied_filters:
                    st.write(f"- {filter_info}")
            else:
                st.write("No se han aplicado filtros.")

            #if 'fullscreen_image' not in st.session_state:
            #    st.session_state.fullscreen_image = None

            # Mostrar imágenes basadas en el DataFrame filtrado
            if st.session_state.fullscreen_image is None:
                for i in range(0, len(filtered_df), 4):
                    row_data = filtered_df.iloc[i:i+4]
                    cols = st.columns(len(row_data))

                    for col_index, (_, row) in enumerate(row_data.iterrows()):
                        image_name = row['ID_jpg']
                        if isinstance(image_name, str):
                            if image_name.startswith('a_') and image_name in images1:
                                image_path = images1[image_name]
                            elif image_name.startswith('o_') and image_name in images2:
                                image_path = images2[image_name]
                            else:
                                continue

                            # Muestra la imagen
                            cols[col_index].image(image_path, caption=image_name, use_column_width=True)
                            
                            # Crea un botón para toggle de la imagen en pantalla completa
                            if cols[col_index].button(f"Ver imagen completa", key=f"btn_{image_name}"):
                                toggle_fullscreen(image_name)
                                st.experimental_rerun()

                    st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)
            else:
                # Muestra la imagen en pantalla completa
                col1, col2 = st.columns([3, 2])
                with col1:
                    if st.session_state.fullscreen_image.startswith('a_'):
                        fullscreen_image_path = images1[st.session_state.fullscreen_image]
                    else:
                        fullscreen_image_path = images2[st.session_state.fullscreen_image]
                    st.image(fullscreen_image_path, caption=st.session_state.fullscreen_image, use_column_width=True)
                with col2:
                    st.subheader("Detalles de la imagen")
                    fullscreen_row = filtered_df[filtered_df['ID_jpg'] == st.session_state.fullscreen_image].iloc[0]
                    show_image_details(fullscreen_row.to_dict())
                
                # Botón para cerrar la vista de pantalla completa
                if st.button("Cerrar imagen completa", key="close_fullscreen"):
                    st.session_state.fullscreen_image = None
                    st.experimental_rerun()

                st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

            # Añade el botón de descarga para las imágenes filtradas
            if len(filtered_df) > 0:
                zip_buffer = create_downloadable_zip(filtered_df, images1, images2)
                st.download_button(
                    label="Descargar imágenes filtradas como ZIP",
                    data=zip_buffer,
                    file_name="filtered_images.zip",
                    mime="application/zip"
                )
        else:
            st.error("No se encontró el archivo df_results.csv en el ZIP.")

    else:
        st.error("No se encontraron las carpetas NEUTRAL y OLDER en el archivo ZIP.")

    os.remove(temp_zip_path)
    shutil.rmtree(temp_extract_path, ignore_errors=True)