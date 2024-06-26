import streamlit as st
from zipfile import ZipFile
import os
import shutil
from PIL import Image
import re
import pandas as pd
import io
from st_aggrid import AgGrid

# Function to get metadata from a PNG image
def get_png_metadata(image_path):
    try:
        image = Image.open(image_path)
        image.load()  # Load the image to read the metadata
        return image.info
    except ImportError:
        return {}

# Function to extract a ZIP file
def extract_zip(zip_path, extract_to):
    with ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

# Function to read images from a folder and sort them naturally
def read_images_from_folder(folder_path):
    images = {}
    filenames = sorted(os.listdir(folder_path), key=natural_sort_key)
    for filename in filenames:
        if filename.endswith(".png"):
            image_path = os.path.join(folder_path, filename)
            images[filename] = image_path
    return images

# Function to format metadata
def format_metadata(metadata):
    if 'Negative prompt:' in metadata:
        parts = metadata.split('Negative prompt:', 1)
        prompt = parts[0].strip()
        rest = 'Negative prompt:' + parts[1]
    else:
        prompt = metadata
        rest = ""
    
    return prompt, rest

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

    # Read the DataFrame from the ZIP file
    df_results = read_dataframe_from_zip(temp_zip_path)
    if df_results is not None:
        AgGrid(df_results, height=500, width='100%', fit_columns_on_grid_load=True, enable_enterprise_modules=False)
    else:
        st.error("No se encontró el archivo df_results.csv en el ZIP.")

    st.divider()

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

        # Store metadata for each image
        metadata_dict = {}
        for image_name in images1.keys():
            metadata1 = get_png_metadata(images1[image_name])
            metadata_dict[image_name] = (metadata1, None)
        for image_name in images2.keys():
            metadata2 = get_png_metadata(images2[image_name])
            if image_name in metadata_dict:
                metadata_dict[image_name] = (metadata_dict[image_name][0], metadata2)
            else:
                metadata_dict[image_name] = (None, metadata2)

        # Convert JPG filenames in df_results to PNG filenames
        df_results['ID_png'] = df_results['ID_jpg'].str.replace('.jpg', '.png')

        # Display images in rows of four
        for i in range(0, len(images1), 4):  # 4 parejas por fila
            row_images = list(images1.keys())[i:i+4]
            cols = st.columns(len(row_images) * 2)  # Each image pair has two columns

            for col_index, image_name in enumerate(row_images):
                if image_name.startswith('a'):
                    corresponding_older_image = image_name.replace('a_', 'o_')
                    if corresponding_older_image in images2:
                        image1_path = images1[image_name]
                        image2_path = images2[corresponding_older_image]

                        # Neutral image
                        cols[col_index*2].image(image1_path, caption=image_name, use_column_width=True)
                        metadata1 = get_png_metadata(image1_path)
                        prompt1, details1 = format_metadata(metadata1.get('parameters', ''))

                        with cols[col_index*2].expander("Ver detalles"):
                            st.markdown(f"**Prompt:**\n{prompt1}\n\n**Labels (AWS):**")
                            if df_results is not None:
                                labels1 = df_results.loc[df_results['ID_png'] == image_name, 'labels_aws'].values
                                if len(labels1) > 0:
                                    st.markdown(labels1[0])
                            st.markdown("**Output (Kosmos):**")
                            if df_results is not None:
                                labels1 = df_results.loc[df_results['ID_png'] == image_name, 'output_kosmos'].values
                                if len(labels1) > 0:
                                    st.markdown(labels1[0])
                            st.markdown("**Labels (Kosmos):**")
                            if df_results is not None:
                                labels1 = df_results.loc[df_results['ID_png'] == image_name, 'labels_kosmos'].values
                                if len(labels1) > 0:
                                    st.markdown(labels1[0])

                        # Older image
                        cols[col_index*2+1].image(image2_path, caption=corresponding_older_image, use_column_width=True)
                        metadata2 = get_png_metadata(image2_path)
                        prompt2, details2 = format_metadata(metadata2.get('parameters', ''))

                        with cols[col_index*2+1].expander("Ver detalles"):
                            st.markdown(f"**Prompt:**\n{prompt2}\n\n**Labels (AWS):**")
                            if df_results is not None:
                                labels2 = df_results.loc[df_results['ID_png'] == corresponding_older_image, 'labels_aws'].values
                                if len(labels2) > 0:
                                    st.markdown(labels2[0])
                            st.markdown("**Output (Kosmos):**")
                            if df_results is not None:
                                labels2 = df_results.loc[df_results['ID_png'] == corresponding_older_image, 'output_kosmos'].values
                                if len(labels2) > 0:
                                    st.markdown(labels2[0])
                            st.markdown("**Labels (Kosmos):**")
                            if df_results is not None:
                                labels2 = df_results.loc[df_results['ID_png'] == corresponding_older_image, 'labels_kosmos'].values
                                if len(labels2) > 0:
                                    st.markdown(labels2[0])

            # Add horizontal line after each row of images
            st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    # Remove temporary files and folders
    os.remove(temp_zip_path)
    shutil.rmtree(temp_extract_path, ignore_errors=True)
