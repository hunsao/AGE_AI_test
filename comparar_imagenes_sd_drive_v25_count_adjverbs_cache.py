import streamlit as st
from zipfile import ZipFile
import os
import shutil
from PIL import Image
import re
import json
import pandas as pd
import io
import base64
import time

from st_aggrid import AgGrid
from streamlit import cache_data
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_httplib2 import Request
from googleapiclient.errors import HttpError

st.set_page_config(layout="wide")

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.df_results = None
    st.session_state.images1 = None
    st.session_state.images2 = None

@cache_data(ttl=3600)
def count_observations(df, category, options):
    if category in ['adj_image', 'adj_person', 'verbs', 'position_short']:
        return {option: df[df[category].apply(lambda x: option in eval(x) if isinstance(x, str) else False)].shape[0] for option in options}
    elif category in ['shoot', 'activities']:
        return {option: df['Prompt'].str.contains(option, case=False, na=False).sum() for option in options}
    elif category == 'Prompt':
        return {option: df[category].str.contains(option, case=False, na=False).sum() for option in options}
    else:
        return {option: df[df[category] == option].shape[0] for option in options}

@cache_data(ttl=3600)
def get_sorted_options(df, category, options):
    if category in ['shoot', 'activities']:
        column = 'Prompt'
    else:
        column = category
    
    counts = count_observations(df, category, options)
    options_with_count = sorted([(option, count) for option, count in counts.items()], key=lambda x: x[1], reverse=True)
    return [f"{option} ({count})" for option, count in options_with_count]

@st.cache_data(ttl=3600)
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

@cache_data(ttl=3600)
def get_unique_list_items(df, column):
    all_items = [item for sublist in df[column].dropna() for item in eval(sublist) if isinstance(sublist, str)]
    return sorted(set(all_items))

# Google Drive API#

# Function to get Google Drive service
#def get_drive_service():
#    try:
#        SERVICE_ACCOUNT_FILE = 'TEST/STREAMLIT/tranquil-hawk-429712-r9-ca222fe2b5cb.json'
#        credentials = service_account.Credentials.from_service_account_file(
#            SERVICE_ACCOUNT_FILE,
#            scopes=['https://www.googleapis.com/auth/drive.readonly']
#        )
#        service = build('drive', 'v3', credentials=credentials)
#        return service
#    except Exception as e:
#        st.error(f"Error al obtener el servicio de Google Drive: {str(e)}")
#        return None

def get_drive_service():
    try:
        # Obtener el secreto de Streamlit
        encoded_sa = st.secrets["GOOGLE_SERVICE_ACCOUNT"]

        # Decodificar la cadena
        sa_json = base64.b64decode(encoded_sa).decode('utf-8')

        # Crear un diccionario a partir de la cadena JSON
        sa_dict = json.loads(sa_json)

        # Crear las credenciales
        credentials = service_account.Credentials.from_service_account_info(
            sa_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )

        # Construir el servicio
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        st.error(f"Error al obtener el servicio de Google Drive: {str(e)}")
        return None

def list_files_in_folder(service, folder_id):
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            fields="files(id, name)"
        ).execute()
        return results.get('files', [])
    except HttpError as error:
        st.error(f"Error al listar archivos: {error}")
        st.error(f"Error details: {error.content.decode('utf-8')}")  # Add this line
        return []

# Clase para ajustar el tiempo de espera de la solicitud
class RequestWithTimeout(Request):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = 120  # Ajusta el tiempo de espera aquí (en segundos)

# Función para descargar archivo desde Google Drive
def download_file_from_google_drive(service, file_id, dest_path):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(dest_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            #st.write(f'Download {int(status.progress() * 100)}%')
        
        fh.close()
        #st.success(f"Archivo descargado correctamente: {dest_path}")
        st.success(f"Archivo descargado correctamente")
    except Exception as e:
        st.error(f"Error al descargar el archivo: {str(e)}")

# Función para extraer el ZIP
def extract_zip(zip_path, extract_to):
    try:
        with ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        #st.success(f"Archivo ZIP extraído correctamente en: {extract_to}")
        #st.write(f"Contenido de {extract_to}:")
        st.write(os.listdir(extract_to))
    except Exception as e:
        st.error(f"Error al extraer el archivo ZIP: {str(e)}")

def extract_folder_id(url):
    """Extract the folder ID from a Google Drive URL."""
    match = re.search(r'folders/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None

############################################################################

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

@cache_data(ttl=3600)
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
                zip_file

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

def get_unique_list_items(df, column):
    all_items = [item for sublist in df[column].dropna() for item in eval(sublist) if isinstance(sublist, str)]
    return sorted(set(all_items))

#############################################################################################################################
st.markdown("<h1 style='text-align: center; color: white;'>AGEAI: Imágenes y Metadatos</h1>", unsafe_allow_html=True)

if not st.session_state.data_loaded:
    # Conexión con Google Drive
    service = get_drive_service()
    if service is None:
        st.error("No se pudo establecer la conexión con Google Drive.")
        st.stop()
    else:
        success_message = st.empty()
        success_message.success("Conexión a Google Drive establecida correctamente.")
        time.sleep(3)
        success_message.empty()

    folder_url = st.text_input(
        "Ingrese el enlace de la carpeta de Google Drive:",
        value="https://drive.google.com/drive/u/0/folders/1Zx1ifjBGx_oPUtmtwkrWBMgCvoQ5R2w7"
    )

    folder_id = extract_folder_id(folder_url)

    if not folder_id:
        st.warning("Por favor, ingrese un enlace de carpeta de Google Drive válido.")
        st.stop()

    files = list_files_in_folder(service, folder_id)
    #st.write(f"Número de archivos encontrados: {len(files)}")

    if not files:
        st.error("No se encontraron archivos en la carpeta de Google Drive.")
        st.stop()

    file_options = {item['name']: item['id'] for item in files if item['name'].endswith('.zip')}
    selected_file_name = st.selectbox("Selecciona el archivo ZIP:", list(file_options.keys()))

    if selected_file_name and st.button("Confirmar selección"):
        # Descargar y extraer el ZIP
        file_id = file_options[selected_file_name]
        temp_zip_path = "temp.zip"
        download_file_from_google_drive(service, file_id, temp_zip_path)
        temp_extract_path = "extracted_folders"
        extract_zip(temp_zip_path, temp_extract_path)
        
        # Cargar datos en la sesión
        if os.path.exists(temp_extract_path):
            folder1 = os.path.join(temp_extract_path, 'NEUTRAL')
            folder2 = os.path.join(temp_extract_path, 'OLDER')
            st.session_state.images1 = read_images_from_folder(folder1)
            st.session_state.images2 = read_images_from_folder(folder2)
            st.session_state.df_results = read_dataframe_from_zip(temp_zip_path)
            
            if st.session_state.df_results is not None:
                st.session_state.df_results = st.session_state.df_results.dropna(subset=['ID', 'ID_jpg', 'Prompt'])
                st.session_state.df_results['gender'] = st.session_state.df_results['Prompt'].apply(lambda x: 'woman' if 'woman' in x.lower().split() else ('man' if 'man' in x.lower().split() else 'person'))
                st.session_state.data_loaded = True
                st.success("Datos cargados correctamente. La página se actualizará automáticamente.")
                st.experimental_rerun()
            else:
                st.error("No se pudo cargar el DataFrame.")
        
        # Limpiar archivos temporales
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path, ignore_errors=True)


# Parte 2: Mostrar el dashboard
else:
    df_results = st.session_state.df_results
    images1 = st.session_state.images1
    images2 = st.session_state.images2
    #selected_age_ranges = []

    st.sidebar.header("Filtrar Imágenes")
    group_filter = st.sidebar.selectbox("Seleccionar Grupo", ["Todos", "NEUTRAL", "OLDER"], index=0)

    filtered_df = df_results.copy()

    # Aplicar filtro de grupo primero
    if group_filter == "NEUTRAL":
        filtered_df = df_results[df_results['ID'].str.startswith('a_')]
    elif group_filter == "OLDER":
        filtered_df = df_results[df_results['ID'].str.startswith('o_')]
    #else:
    #    filtered_df = df_results.copy()  # Usar una copia para evitar modificar el original

    # Inicializar categorías una vez al cargar los datos
    if 'categories' not in st.session_state:
        st.session_state.categories = {
            "shoot": ["full shot", "close-up shot"],
            "gender": ["woman", "man", "person"],
            "activities": ["walking", "eating", "dressing", "taking a shower", "get pissed", "toileting", "ordering a taxi", "paying bills", "shopping", "doing home chores",
                        "using the phone", "at home", "in the living room", "in a room", "in winter"],
            "emotions_short": ["neutral", "positive", "negative", "none"],
            "personality_short": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
            "location": ["indoors", "outdoors", "none"]
        }
        
        # Añadir nuevas categorías
        new_categories = ["adj_image", "adj_person", "verbs", "position_short"]
        for category in new_categories:
            st.session_state.categories[category] = get_unique_list_items(df_results, category)

    # Usar las categorías almacenadas en la sesión
    categories = st.session_state.categories

    if 'reset_filters' not in st.session_state:
        st.session_state.reset_filters = False

    if st.sidebar.button("Resetear Filtros"):
        st.session_state.reset_filters = True
        for key in st.session_state.keys():
            if key.startswith('multiselect_'):
                st.session_state[key] = []

    for category, options in categories.items():
        selected = st.sidebar.multiselect(
            f"Seleccionar {category.replace('_', ' ').title()}",
            get_sorted_options(df_results, category, options),
            default=get_default(category),
            key=f"multiselect_{category}"
        )
        
        selected_options = [option.split(" (")[0] for option in selected]
        
        if selected_options:
            if category in ["shoot", "activities"]:
                filtered_df = filtered_df[filtered_df['Prompt'].apply(lambda x: any(item.lower() in x.lower() for item in selected_options))]
            elif category in ['adj_image', 'adj_person', 'verbs', 'position_short']:
                filtered_df = filtered_df[filtered_df[category].apply(lambda x: any(item in eval(x) for item in selected_options) if isinstance(x, str) else False)]
            else:
                filtered_df = filtered_df[filtered_df[category].isin(selected_options)]

    # Filtro de Age Range  
    age_ranges = sorted(df_results['age_range'].unique().tolist())
    selected_age_ranges = st.sidebar.multiselect(
        "Seleccionar Age Range",
        get_sorted_options(df_results, 'age_range', age_ranges),
        default=get_default("age_ranges"),
        key="multiselect_age_ranges"
    )

    selected_age_ranges = [age.split(" (")[0] for age in selected_age_ranges]
    if selected_age_ranges:
        filtered_df = filtered_df[filtered_df['age_range'].isin(selected_age_ranges)]

    if st.session_state.reset_filters:
        st.session_state.reset_filters = False

    st.sidebar.header("Buscador de Variables")
    search_columns = df_results.columns.tolist()
    selected_column = st.sidebar.selectbox("Seleccionar Variable para Buscar", search_columns)
    search_term = st.sidebar.text_input(f"Buscar en {selected_column}")

    # Aplicar búsqueda
    if search_term:
        filtered_df = filtered_df[filtered_df[selected_column].astype(str).str.contains(search_term, case=False, na=False)]

    # Mostrar DataFrame filtrado
    AgGrid(filtered_df, height=600, width='100%', fit_columns_on_grid_load=False, enable_enterprise_modules=False)

    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="Descargar DataFrame Filtrado",
        data=csv,
        file_name="filtered_dataframe.csv",
        mime="text/csv",
    )

    # Mostrar imágenes filtradas
    st.divider()
    st.write(f"Número de imágenes filtradas: {len(filtered_df)}")

    # Mostrar filtros aplicados
    applied_filters = []
    if group_filter != "Todos":
        applied_filters.append(f"Grupo: {group_filter}")
    for category in categories:
        selected = st.session_state.get(f"multiselect_{category}", [])
        if selected:
            applied_filters.append(f"{category.replace('_', ' ').title()}: {', '.join([s.split(' (')[0] for s in selected])}")
    if selected_age_ranges:
        applied_filters.append(f"Age Range: {', '.join(selected_age_ranges)}")
    if search_term:
        applied_filters.append(f"Búsqueda: '{search_term}' en '{selected_column}'")

    if applied_filters:
        st.write("Filtros aplicados:")
        for filter_info in applied_filters:
            st.write(f"- {filter_info}")
    else:
        st.write("No se han aplicado filtros.")

    # Mostrar imágenes
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
                    cols[col_index].image(image_path, caption=image_name, use_column_width=True)
                    if cols[col_index].button(f"Ver imagen completa", key=f"btn_{image_name}"):
                        toggle_fullscreen(image_name)
                        st.experimental_rerun()
        st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    else:
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
        if st.button("Cerrar imagen completa", key="close_fullscreen"):
            st.session_state.fullscreen_image = None
            st.experimental_rerun()
        st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    # Botón para descargar imágenes filtradas como ZIP
    if len(filtered_df) > 0:
        zip_buffer = create_downloadable_zip(filtered_df, images1, images2)
        st.download_button(
            label="Descargar imágenes filtradas como ZIP",
            data=zip_buffer,
            file_name="filtered_images.zip",
            mime="application/zip"
        )
    else:
        st.error("No se encontraron imágenes que cumplan con los filtros aplicados.")

# Limpiar archivos temporales
if 'temp_zip_path' in locals() and temp_zip_path is not None and os.path.exists(temp_zip_path):
    try:
        os.remove(temp_zip_path)
    except Exception as e:
        st.warning(f"Could not remove temporary zip file: {e}")

if 'temp_extract_path' in locals() and temp_extract_path is not None and os.path.exists(temp_extract_path):
    try:
        shutil.rmtree(temp_extract_path, ignore_errors=True)
    except Exception as e:
        st.warning(f"Could not remove temporary extracted folder: {e}")
