import streamlit as st
from PIL import Image
import pandas as pd
from datetime import datetime
import io
import os
import re
import random
import json
import base64

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import socket

# Define the questionnaire structure
questionnaire = {
    "ROUND 1": [
        {
            "question": "P1. Indicate the number of people you see in the image",
            "options": ["0", "1", "2", "3", "+3", "Don't know"],
            "definition": "People is some person than can clearly be identified as a real human. Do not count as a person completely blurry images in the background, or hallucinations (that frequently exist in AI generated images, as a person with 3 hands), or depicted images in a non photorealistic style (ex: cartoon)."
        },
        {
            "question": "P2. Indicate if you are observing people from behind",
            "options": ["Yes", "No", "Don't know"],
            "definition": "From behind means that image shows people from the rear or the back side, rather than from the front or a more visible angle.\n- **Yes:** One person is showed from behind.\n- **No:** No person is showed from behind."
        },
        {
            "question": "P3. Indicate the gender of the person you see in the image",
            "options": ["Female", "Male", "Don't know"],
            "definition": "Despite gender is social construct that 'varies from society to society and can change over time', we use here a simplification of the classification of gender due to the limitations of Computer Vision variables developed."
        }
    ],
    "ROUND 2": [
        {
            "question": "P4. Are there assistive products?",
            "options": ["Yes", "No", "Don't know"],
            "definition": "Assistive products can range from physical products such as wheelchairs, glasses, prosthetic limbs, white canes, and hearing aids to digital solutions such as speech recognition or time management software and captioning"
        }
    ]
}

# def get_google_services():
#     try:
#         credentials = service_account.Credentials.from_service_account_file(
#             SERVICE_ACCOUNT_FILE, scopes=SCOPES
#         )
#         drive_service = build('drive', 'v3', credentials=credentials)
#         sheets_service = build('sheets', 'v4', credentials=credentials)
#         return drive_service, sheets_service
#     except Exception as e:
#         st.error(f"Error al obtener los servicios de Google: {str(e)}")
#         return None, None

class ExponentialBackoffHttpRequest(HttpRequest):
    def __init__(self, *args, **kwargs):
        super(ExponentialBackoffHttpRequest, self).__init__(*args, **kwargs)
        self.max_retries = 5

@st.cache_resource
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((socket.timeout, TimeoutError)))

def get_google_services():
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
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/spreadsheets'
            ]
        )
        
        # Create a custom http object with increased timeout
        http = build_http()
        http.timeout = 60  # Increase timeout to 30 seconds (adjust as needed)

        # Construir los servicios
        drive_service = build('drive', 'v3', credentials=credentials, http=http, requestBuilder=ExponentialBackoffHttpRequest)
        sheets_service = build('sheets', 'v4', credentials=credentials, http=http, requestBuilder=ExponentialBackoffHttpRequest)

        return drive_service, sheets_service
    except Exception as e:
        st.error(f"Error al obtener los servicios de Google: {str(e)}")
        return None, None

def download_file_from_google_drive(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        st.error(f"Error al descargar el archivo: {str(e)}")
        return None

def extract_folder_id(url):
    match = re.search(r'folders/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None

# def find_images_folder_and_csv_id(service, parent_folder_name):
#     try:
#         results = service.files().list(
#             q=f"name='{parent_folder_name}' and mimeType='application/vnd.google-apps.folder'",
#             fields="nextPageToken, files(id)"
#         ).execute()
#         parent_folders = results.get('files', [])
#         if not parent_folders:
#             st.error(f"No se encontró la carpeta principal '{parent_folder_name}'.")
#             return None, None
#         parent_folder_id = parent_folders[0]['id']
#         results = service.files().list(
#             q=f"'{parent_folder_id}' in parents",
#             fields="nextPageToken, files(id, name, mimeType)"
#         ).execute()
#         items = results.get('files', [])
#         images_folder_id = None
#         csv_file_id = None
#         for item in items:
#             if item['name'] == 'IMAGES' and item['mimeType'] == 'application/vnd.google-apps.folder':
#                 images_folder_id = item['id']
#             elif item['name'].endswith('.csv') and item['mimeType'] == 'text/csv':
#                 csv_file_id = item['id']
#         if not images_folder_id:
#             st.error("No se encontró la carpeta 'IMAGES'.")
#         if not csv_file_id:
#             st.error("No se encontró el archivo CSV.")
#         return images_folder_id, csv_file_id
#     except Exception as e:
#         st.error(f"Error al buscar la carpeta 'IMAGES' y el CSV: {str(e)}")
#         return None, None

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_folder_and_file_ids(service, parent_folder_name):
    try:
        # Find the parent folder
        parent_folder_results = service.files().list(
            q=f"name='{parent_folder_name}' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute()
        parent_folders = parent_folder_results.get('files', [])
        if not parent_folders:
            st.error(f"No se encontró la carpeta principal '{parent_folder_name}'.")
            return None, None
        parent_folder_id = parent_folders[0]['id']
        
        # Search for IMAGES folder and CSV file in a single request
        results = service.files().list(
            q=f"'{parent_folder_id}' in parents and (name='IMAGES' or mimeType='text/csv')",
            fields="files(id, name, mimeType)"
        ).execute()
        
        items = results.get('files', [])
        images_folder_id = None
        csv_file_id = None
        
        for item in items:
            if item['name'] == 'IMAGES' and item['mimeType'] == 'application/vnd.google-apps.folder':
                images_folder_id = item['id']
            elif item['mimeType'] == 'text/csv':
                csv_file_id = item['id']
        
        if not images_folder_id:
            st.error("No se encontró la carpeta 'IMAGES'.")
        if not csv_file_id:
            st.error("No se encontró el archivo CSV.")
        
        return images_folder_id, csv_file_id
    except Exception as e:
        st.error(f"Error al buscar la carpeta 'IMAGES' y el CSV: {str(e)}")
        return None, None

@st.cache_data()
def list_images_in_folder(_service, folder_id):
    try:
        results = _service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            fields="nextPageToken, files(id, name)"
        ).execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        st.error(f"Error al listar las imágenes: {str(e)}")
        return []

@st.cache_data()
def download_and_cache_csv(_service, file_id):
    csv_bytes = download_file_from_google_drive(_service, file_id)
    if csv_bytes:
        return pd.read_csv(io.BytesIO(csv_bytes))
    else:
        return None

def save_labels_to_google_sheets(sheets_service, spreadsheet_id, user_id, image_name, labels):
    try:
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[user_id, image_name, current_datetime] + list(labels.values())]
        
        body = {
            'values': values
        }
        
        result = sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='Sheet1',
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()

        st.sidebar.success(f'Respuestas guardadas para la imagen {image_name} en Google Sheets')
    except Exception as e:
        st.error(f"Error al guardar las etiquetas en Google Sheets: {str(e)}")

def main():
    st.set_page_config(layout="wide")

    drive_service, sheets_service = get_google_services()
    
    if not drive_service or not sheets_service:
        st.error("No se pudieron obtener los servicios de Google.")
        return

    drive_url = "https://drive.google.com/drive/u/0/folders/1ii7UIuwg2zhoTNytADMIfW9QKRgg51Bs"
    parent_folder_name = "09_20_LABELLING_TEST"
    spreadsheet_id = "10HgyUYfkiS8LuXXRTTHcO9IzglwTXb6DU7Yu_m9z7yE"

    parent_folder_id = extract_folder_id(drive_url)

    if 'page' not in st.session_state:
        st.session_state.page = 'start'

    if 'current_question' not in st.session_state:
        st.session_state.current_question = 0
        st.session_state.responses = {}

    if 'responses' not in st.session_state:
            st.session_state.responses = {}

    if 'user_id' not in st.session_state:
        st.session_state.user_id = ''

    if 'review_mode' not in st.session_state:
        st.session_state.review_mode = False    

    # Sidebar
    #st.sidebar.title("Progress")

    if parent_folder_id:
        #images_folder_id, csv_file_id = find_images_folder_and_csv_id(drive_service, parent_folder_name)
        images_folder_id, csv_file_id = get_folder_and_file_ids(drive_service, parent_folder_name)
        if images_folder_id and csv_file_id:
            image_list = list_images_in_folder(drive_service, images_folder_id)

            if 'current_image' not in st.session_state:
                st.session_state.current_image = random.choice(image_list)

            if st.session_state.page == 'start':
                col1, col2, col3 = st.columns([1, 2, 1])  # Create 3 columns, middle one wider

                with col2:  # Content will be centered in the middle column
                    st.markdown("<h1 style='text-align: center;'>Welcome to the AGEAI project questionary</h1>", unsafe_allow_html=True)
                    st.markdown("<p style='text-align: center;'>This tool is designed to help us collect data about images for AI training purposes.</p>", unsafe_allow_html=True)
                    st.markdown("<p style='text-align: center;'>You will be presented with a series of images and questions. Please answer them to the best of your ability.</p>", unsafe_allow_html=True)
                    st.markdown("<p style='text-align: center;'>Your responses are valuable and will contribute to improving or findings.</p>", unsafe_allow_html=True)
                    
                    st.session_state.user_id = st.text_input('Enter your user ID', value=st.session_state.user_id)
                    
                    if st.session_state.user_id:
                        if st.button("Start Questionnaire"):
                            st.session_state.page = 'questionnaire'
                            st.rerun()
                    else:
                        st.warning("Please enter your user ID to start the questionnaire.")

            elif st.session_state.page == 'questionnaire':
                # Display progress in sidebar and enable navigation
                for round_name, questions in questionnaire.items():
                    st.sidebar.subheader(round_name)
                    for i, q in enumerate(questions):
                        question_number = i + 1 if round_name == "ROUND 1" else len(questionnaire["ROUND 1"]) + i + 1
                        if st.session_state.review_mode or question_number <= st.session_state.current_question:
                            if st.sidebar.button(f"✅ {q['question'][:100]}...", key=f"nav_{round_name}_{i}"):
                                st.session_state.current_question = question_number - 1
                                st.rerun()
                        else:
                            st.sidebar.button(f"⬜ {q['question'][:100]}...", key=f"nav_{round_name}_{i}", disabled=True)

                # Main content
                col1, col2 = st.columns([2, 3])

                with col1:
                    current_round = "ROUND 1" if st.session_state.current_question < len(questionnaire["ROUND 1"]) else "ROUND 2"
                    current_question = questionnaire[current_round][st.session_state.current_question % len(questionnaire[current_round])]

                    st.title(f"{current_round}")
                    # st.write(f"**Question:**\n{current_question['question']}")
                    # st.write(f"**Definition:** {current_question['definition']}")
                    st.write("### **Question:**")
                    st.write(current_question['question'])
                    st.write("### **Definition:**")
                    st.write(current_question['definition'])

                    # Use the existing response if available, otherwise default to None
                    default_answer = st.session_state.responses.get(current_question["question"])
                    answer = st.radio("Select an option:", current_question["options"], key=f"question_{st.session_state.current_question}", index=None if default_answer is None else current_question["options"].index(default_answer))

                    if st.button("Next Question", key="next_button"):
                        if answer is not None:
                            st.session_state.responses[current_question["question"]] = answer
                            st.session_state.current_question += 1
                            if st.session_state.current_question >= len(questionnaire["ROUND 1"]) + len(questionnaire["ROUND 2"]):
                                st.session_state.page = 'review'
                                st.session_state.review_mode = True
                            else:
                                st.session_state.current_image = random.choice(image_list)
                            st.rerun()
                        else:
                            st.warning("Please select an answer before proceeding.")

                with col2:
                    image_bytes = download_file_from_google_drive(drive_service, st.session_state.current_image['id'])
                    st.image(image_bytes, use_column_width=True)

            elif st.session_state.page == 'review':
                st.title("Cuestionario completado")
                st.write("Has completado todas las preguntas. Puedes revisar tus respuestas o enviar el cuestionario.")

                # Mostrar resumen de respuestas
                #st.subheader("Resumen de respuestas:")
                #for question, answer in st.session_state.responses.items():
                #    st.write(f"**{question}**: {answer}")

                if st.button("Revisar respuestas"):
                    st.session_state.current_question = 0
                    st.session_state.page = 'questionnaire'
                    st.session_state.review_mode = True
                    st.rerun()

                if st.button("Enviar cuestionario"):
                    save_labels_to_google_sheets(sheets_service, spreadsheet_id, st.session_state.user_id, st.session_state.current_image['name'], st.session_state.responses)
                    st.session_state.page = 'end'
                    st.session_state.review_mode = False
                    st.rerun()

            elif st.session_state.page == 'end':
                st.title("Thanks for participating! 😊")
                st.balloons()
                st.write("Your responses have been saved and will be used to improve our AI systems.")
                st.write("We appreciate your time and effort in completing this questionnaire.")
                if st.button("Start New Questionnaire"):
                    st.session_state.current_question = 0
                    st.session_state.responses = {}
                    st.session_state.page = 'start'
                    st.session_state.user_id = ''
                    st.session_state.review_mode = False
                    st.rerun()

    else:
        st.error("No se pudo obtener el ID de la carpeta principal.")

if __name__ == "__main__":
    main()