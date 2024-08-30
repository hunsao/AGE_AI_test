#streamlit run c:/Users/David/Documents/AGEAI/Scripts/TEST/STREAMLIT/comparar_imagenes_sd_drive_v28_ollama.py
import streamlit as st
from zipfile import ZipFile
import os
import json
import shutil
from PIL import Image
import re
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

from googleapiclient.http import HttpRequest
from googleapiclient.http import build_http

http = build_http()
http.timeout = 120 

st.set_page_config(layout="wide")

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.df_results = None
    st.session_state.images1 = None
    st.session_state.images2 = None
    st.session_state.group_filter = "Todos"  # Valor por defecto para el filtro de grupo
    st.session_state.search_term = ""  # Valor por defecto para el término de búsqueda

@st.cache_data()
def count_observations(df, category, options):
    if category in ['activities']:
        return {option: df['prompt'].str.contains(option, case=False, na=False).sum() for option in options}
    elif category == 'prompt':
        return {option: df[category].str.contains(option, case=False, na=False).sum() for option in options}
    else:
        return {option: df[df[category] == option].shape[0] for option in options}

@st.cache_data()
def get_sorted_options(df, category, options):
    if category in ['activities']:
        column = 'prompt'
    else:
        column = category
    
    counts = count_observations(df, category, options)
    options_with_count = sorted([(option, count) for option, count in counts.items()], key=lambda x: x[1], reverse=True)
    return [f"{option} ({count})" for option, count in options_with_count]

@st.cache_data(max_entries=1)
def create_downloadable_zip(filtered_df, images1, images2):
    zip_buffer = io.BytesIO()
    try:
        with ZipFile(zip_buffer, 'w') as zip_file:
            for _, row in filtered_df.iterrows():
                image_name = row.get('filename_jpg')  
                group_id = row.get('ID')
                
                if image_name is None:
                    st.error("No se encontró el nombre de la imagen en la fila.")
                    continue
                
                if group_id is None:
                    st.error("No se encontró el ID del grupo en la fila.")
                    continue
                
                if isinstance(image_name, str) and isinstance(group_id, str):
                    if group_id.startswith('a_'):
                        image_path = images1.get(image_name, None)
                        folder_name = 'NEUTRAL'
                    elif group_id.startswith('o_'):
                        image_path = images2.get(image_name, None)
                        folder_name = 'OLDER'
                    else:
                        st.warning(f"ID del grupo no coincide con ningún grupo conocido: {group_id}")
                        continue
                    
                    if image_path:
                        zip_file.write(image_path, os.path.join(folder_name, image_name))
                    else:
                        st.warning(f"No se encontró la imagen en el diccionario de imágenes: {image_name}")
    except Exception as e:
        st.error(f"Error al crear el archivo ZIP: {str(e)}")
    finally:
        zip_buffer.seek(0)
    return zip_buffer

# def get_drive_service():
#     try:
#         SERVICE_ACCOUNT_FILE = 'TEST/STREAMLIT/tranquil-hawk-429712-r9-ca222fe2b5cb.json'
#         credentials = service_account.Credentials.from_service_account_file(
#             SERVICE_ACCOUNT_FILE,
#             scopes=['https://www.googleapis.com/auth/drive.readonly']
#         )

#         def custom_request(*args, **kwargs):
#             request = HttpRequest(*args, **kwargs)
#             request.timeout = 120  # Aumentar el tiempo de espera a 120 segundos
#             return request

#         service = build('drive', 'v3', credentials=credentials, requestBuilder=custom_request)
#         return service
    
#     except Exception as e:
#         st.error(f"Error al obtener el servicio de Google Drive: {str(e)}")
#         return None

#@st.cache_data()
@st.cache_resource
def get_drive_service():
    try:
        # Obtener la cadena codificada de la variable de entorno
        encoded_sa = os.getenv('GOOGLE_SERVICE_ACCOUNT')
        if not encoded_sa:
            raise ValueError("La variable de entorno GOOGLE_SERVICE_ACCOUNT no está configurada")

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

#@st.cache_data()
#@st.cache_data(ttl=3600)  # Cache for 1 hour
def list_files_in_folder(service, folder_id, retries=3):
    for attempt in range(retries):
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name)"
            ).execute()
            return results.get('files', [])
        except HttpError as error:
            st.error(f"Error al listar archivos (intento {attempt+1}): {error}")
            if attempt < retries - 1:
                time.sleep(5)  # Espera antes de reintentar
            else:
                raise
            
class RequestWithTimeout(Request):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = 120  # Ajusta el tiempo de espera aquí (en segundos)

# Función para descargar archivo desde Google Drive
def download_file_from_google_drive(service, file_id, dest_path, retries=3):
    for attempt in range(retries):
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
            return
        except Exception as e:
            st.error(f"Error al descargar el archivo (intento {attempt+1}): {str(e)}")
            if attempt < retries - 1:
                time.sleep(5)  # Espera antes de reintentar
            else:
                raise

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

@st.cache_data()
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
#@st.cache_data()
@st.cache_data(persist="disk")
def read_images_from_folder(folder_path):
    images = {}
    filenames = sorted(os.listdir(folder_path), key=natural_sort_key)
    for filename in filenames:
        #if filename.endswith(".jpg"):
        if filename.lower().endswith((".jpg", ".jpeg")):
            image_path = os.path.join(folder_path, filename)
            images[filename] = image_path
    return images

# Natural sort function
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

#@st.cache_data(max_entries=1)
@st.cache_data(persist="disk")
def read_dataframe_from_zip(zip_path):
    with ZipFile(zip_path, 'r') as zip_ref:
        if 'df_results.csv' in zip_ref.namelist():
            with zip_ref.open('df_results.csv') as csv_file:
                return pd.read_csv(io.BytesIO(csv_file.read()))
    return None

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

#st.cache_data()
@st.cache_data(persist="disk")
def get_unique_list_items(df_results, category):
    if category in df_results.columns:
        all_items = df_results[category].dropna().tolist()
        
        # Convertir diccionarios a tuplas de valores para hacerlos hashables
        unique_items = set()
        for item in all_items:
            if isinstance(item, dict):
                item = tuple(sorted(item.items()))  # Convertir dict a tupla de pares clave-valor
            unique_items.add(item)
        
        return sorted(unique_items)
    return []

@st.cache_data()
def get_unique_objects(df_results, column_name):
    unique_objects = set()
    for _, row in df_results.iterrows():
        objects_list = row[column_name]
        if isinstance(objects_list, list):
            unique_objects.update(objects_list)
    return sorted(list(unique_objects))

#############################################################################################################################
st.markdown("<h1 style='text-align: center; color: white;'>AGEAI: Imágenes y Metadatos</h1>", unsafe_allow_html=True)

# Inicializar categorías fuera del bloque if/else
if 'categories' not in st.session_state:
    st.session_state.categories = {
        "shot": ["full shot", "close-up shot", "medium shot"],
        "gender": ["male", "female", "none"],
        "race": ["asian", "white", "black", "hispanic", "other"],
        "activities": [
                "walking to the bathroom","in his or her room","climbing stairs","at the dining table","setting the table","selecting clothes","putting on clothes",
                "doing laundry","taking a bath","brushing teeth","grooming","using a toilet","in the bathroom","cleaning the bathroom",
                "planning commuting","booking a travel","commuting","shopping","paying bills","budgeting",
                "planning shopping",
                "preparing meals",
                "storing groceries",
                "dusting",
                "organizing spaces",
                "making phone calls",
                "sending emails",
                "writing a letter",
                "managing medication",
                "calling friends",
                "talking",
                "staying in touch",
                "receiving friends",
                "playing games",
                "in a movie night",
                "in a club meeting",
                "attending a webinar",
                "in a study group",
                "praying",
                "in the living room",
                "taking care of plants",
                "doing an exercise routine",
                "meditating",
                "writing",
                "doing physical therapy",
                "doing puzzles",
                "taking courses",
                "running home-based business",
                "home monitoring",
                "doing diet and nutrition planning",
                "taking medications",
                "using incontinence products",
                "cleaning up spills",
                "in a job fair",
                "volunteering",
                "at the hospital",
                "at work",
                "attending a support group",
                "playing mental games",
                "doing cognitive games",
                "functional outdoor activities",
                "landscaping",
                "participating in community gardens",
                "doing physical activity",
                "playing a sport",
                "in a family meeting",
                "drinking coffee",
                "dining out",
                "participating in community events",
                "in a conference",
                "in a football match",
                "attending religious services",
                "visiting farmers markets",
                "eating out",
                "gardening",
                "doing home repairs",
                "taking out the trash",
                "sending mail",
                "meeting face to face",
                "in a social gathering",
                "buying medications",
                "consulting the doctors",
                "in medical examinations",
                "visiting stores",
                "checking bank accounts",
                "withdrawing money",
                "meeting financial advisors",
                "using public transport",
                "driving",
                "changing incontinence products",
                "attending a medical appointment",
                "walking to a store",
                "strolling in the neighborhood",
                "walking in the metro",
                "dining at a restaurant",
                "shopping groceries",
                "picnicking",
                "shopping clothes",
                "attending fittings",
                "hanging laundry",
                "in a hair salon",
                "using a restroom",
                "buying personal care products"],
        "emotions_short": ["neutral", "positive", "negative", "exaggerated"],
        "personality_short": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
        "position_short": [],
        "person_count": ["1", "2", "3"],
        "location": ["indoors", "outdoors", "'not possible to identify'"],
        "objects": [],  
        "objects_assist_devices": [],  
        "objects_digi_devices": []  
    }
    
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
        value="https://drive.google.com/drive/u/0/folders/1j9r4MWwdP8utL6pF5vHYnCYKWlZwwboi"
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

            st.write("Contenido de la carpeta extraída:", os.listdir(temp_extract_path))

            data_folder = os.path.join(temp_extract_path, 'data')
            folder1 = os.path.join(data_folder, 'NEUTRAL')
            folder2 = os.path.join(data_folder, 'OLDER')
            
            if os.path.exists(folder1) and os.path.exists(folder2):
                st.session_state.images1 = read_images_from_folder(folder1)
                st.session_state.images2 = read_images_from_folder(folder2)
                st.session_state.df_results = read_dataframe_from_zip(temp_zip_path)
                
                # Buscar y cargar cualquier archivo CSV que comience con "df_"
                csv_files = [f for f in os.listdir(data_folder) if f.startswith('df_') and f.endswith('.csv')]
                if csv_files:
                    csv_file_path = os.path.join(data_folder, csv_files[0])
                    st.session_state.df_results = pd.read_csv(csv_file_path)
                
                if st.session_state.df_results is not None:
                    st.session_state.df_results = st.session_state.df_results.dropna(subset=['ID', 'filename_jpg', 'prompt'])
                    
                    new_categories = ["shot", "gender", "race", "emotions_short", "personality_short", "position_short", "person_count", "location",
                                      "objects", "objects_assist_devices", "objects_digi_devices"] 
                    for category in new_categories:
                        st.session_state.categories[category] = get_unique_list_items(st.session_state.df_results, category)
                    
                    st.session_state.data_loaded = True
                    st.success("Datos cargados correctamente. La página se actualizará automáticamente.")
                    st.rerun()
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

    st.sidebar.header("Filtrar Imágenes")

    group_filter = st.sidebar.selectbox("Seleccionar Grupo", ["Todos", "NEUTRAL", "OLDER"], index=["Todos", "NEUTRAL", "OLDER"].index(st.session_state.group_filter))
    st.session_state.group_filter = group_filter

    filtered_df = df_results.copy()

    if group_filter == "NEUTRAL":
        filtered_df = df_results[df_results['age_group'] == 'neutral']
    elif group_filter == "OLDER":
        filtered_df = df_results[df_results['age_group'] == 'older']

    # Usar las categorías almacenadas en la sesión
    categories = st.session_state.categories

    if 'reset_filters' not in st.session_state:
        st.session_state.reset_filters = False

    # Filtro de Age Range (aplicado antes de los demás filtros)
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

    if st.sidebar.button("Resetear Filtros"):
        st.session_state.reset_filters = True
        st.session_state.group_filter = "Todos"
        st.session_state.search_term = ""
        for key in st.session_state.keys():
            if key.startswith('multiselect_'):
                st.session_state[key] = []
        st.rerun()

    for category, options in categories.items():
        selected = st.sidebar.multiselect(
            f"Seleccionar {category.replace('_', ' ').title()}",
            get_sorted_options(df_results, category, options),
            default=get_default(category),
            key=f"multiselect_{category}"
        )
        
        selected_options = [option.split(" (")[0] for option in selected]
        
        if selected_options:
            if category in ["activities"]:
                filtered_df = filtered_df[filtered_df['prompt'].apply(lambda x: any(item.lower() in x.lower() for item in selected_options))]
            else:
                filtered_df = filtered_df[filtered_df[category].isin(selected_options)]

        # Filtro de Objetos
    unique_objects = get_unique_objects(df_results, "objects")
    selected_objects = st.sidebar.multiselect(
        "Seleccionar Objetos",
        unique_objects,
        default=get_default("objects"),
        key="multiselect_objects"
    )

    # Filtro de Objetos Assist Devices
    unique_assist_devices = get_unique_objects(df_results, "objects_assist_devices")
    selected_assist_devices = st.sidebar.multiselect(
        "Seleccionar Objetos Assist Devices",
        unique_assist_devices,
        default=get_default("objects_assist_devices"),
        key="multiselect_objects_assist_devices"
    )

    # Filtro de Objetos Digi Devices
    unique_digi_devices = get_unique_objects(df_results, "objects_digi_devices")
    selected_digi_devices = st.sidebar.multiselect(
        "Seleccionar Objetos Digi Devices",
        unique_digi_devices,
        default=get_default("objects_digi_devices"),
        key="multiselect_objects_digi_devices"
    )

    # Aplicar filtros de objetos
    if selected_objects:
        filtered_df = filtered_df[filtered_df['objects'].apply(lambda x: any(item in x for item in selected_objects))]
    if selected_assist_devices:
        filtered_df = filtered_df[filtered_df['objects_assist_devices'].apply(lambda x: any(item in x for item in selected_assist_devices))]
    if selected_digi_devices:
        filtered_df = filtered_df[filtered_df['objects_digi_devices'].apply(lambda x: any(item in x for item in selected_digi_devices))]

    if st.session_state.reset_filters:
        st.session_state.reset_filters = False

    st.sidebar.header("Buscador de Variables")
    search_columns = df_results.columns.tolist()
    selected_column = st.sidebar.selectbox("Seleccionar Variable para Buscar", search_columns)
    
    # Aplicar búsqueda
    search_term = st.sidebar.text_input(f"Buscar en {selected_column}", value=st.session_state.search_term)
    st.session_state.search_term = search_term  # Actualizar el valor en la sesión
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
                image_name = row['filename_jpg']
                if isinstance(image_name, str):
                    image_path = None
                    if image_name in images1:
                        image_path = images1[image_name]
                    elif image_name in images2:
                        image_path = images2[image_name]

                    if image_path:
                        cols[col_index].image(image_path, caption=image_name, use_column_width=True)
                        if cols[col_index].button(f"Ver imagen completa", key=f"btn_{image_name}"):
                            toggle_fullscreen(image_name)
                            st.rerun()
            st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    else:
        col1, col2 = st.columns([3, 2])
        with col1:
            fullscreen_image_path = None
            if st.session_state.fullscreen_image in images1:
                fullscreen_image_path = images1[st.session_state.fullscreen_image]
            elif st.session_state.fullscreen_image in images2:
                fullscreen_image_path = images2[st.session_state.fullscreen_image]

            if fullscreen_image_path:
                st.image(fullscreen_image_path, caption=st.session_state.fullscreen_image, use_column_width=True)
            else:
                st.error("No se pudo encontrar la imagen para mostrar en pantalla completa.")
                
        with col2:
            st.subheader("Detalles de la imagen")
            fullscreen_row = filtered_df[filtered_df['filename_jpg'] == st.session_state.fullscreen_image]
            if not fullscreen_row.empty:
                show_image_details(fullscreen_row.iloc[0].to_dict())
            else:
                st.warning("No se encontraron detalles para esta imagen.")
        
        if st.button("Cerrar imagen completa", key="close_fullscreen"):
            st.session_state.fullscreen_image = None
            st.rerun()
        st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    # Botón para descargar imágenes filtradas como ZIP
    if len(filtered_df) > 0:
        zip_buffer = create_downloadable_zip(filtered_df, images1, images2)
        if zip_buffer and zip_buffer.getbuffer().nbytes > 0:
            st.download_button(
                label="Descargar imágenes filtradas como ZIP",
                data=zip_buffer,
                file_name="filtered_images.zip",
                mime="application/zip"
            )
        else:
            st.error("No se pudo crear el archivo ZIP.")
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
