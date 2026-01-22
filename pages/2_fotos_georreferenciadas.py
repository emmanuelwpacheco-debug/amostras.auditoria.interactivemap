import streamlit as st
import pandas as pd
import gpxpy
import gpxpy.gpx
from PIL import Image
from PIL.ExifTags import TAGS
import datetime
import simplekml
import io

st.set_page_config(page_title="Geotagueamento de Fotos", layout="wide")

st.title("📸 Georreferenciamento de Evidências")

# --- SIDEBAR ---
st.sidebar.header("Upload de Dados")
gpx_file = st.sidebar.file_uploader("Arquivo GPS (GPX)", type=['gpx'])
fotos = st.sidebar.file_uploader("Fotografias (JPG)", type=['jpg', 'jpeg'], accept_multiple_files=True)

# --- FUNÇÕES TÉCNICAS ---
def extrair_data_foto(foto):
    img = Image.open(foto)
    exif = img._getexif()
    if not exif:
        return None
    for tag_id, value in exif.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == 'DateTimeOriginal':
            return datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
    return None

def processar_gpx(gpx_raw):
    gpx = gpxpy.parse(gpx_raw)
    pontos = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                pontos.append({
                    'time': point.time.replace(tzinfo=None),
                    'lat': point.latitude,
                    'lon': point.longitude,
                    'alt': point.elevation
                })
    return pd.DataFrame(pontos)

# --- LÓGICA PRINCIPAL ---
if gpx_file and fotos:
    df_gps = processar_gpx(gpx_file)
    st.success(f"Tracklog processado: {len(df_gps)} pontos de GPS encontrados.")

    if st.button("Sincronizar Fotos e Gerar KML"):
        kml = simplekml.Kml()
        encontrados = 0
        
        progress_bar = st.progress(0)
        for i, foto_file in enumerate(fotos):
            dt_foto = extrair_data_foto(foto_file)
            
            if dt_foto:
                # Busca o ponto GPS mais próximo no tempo (tolerância de 30s)
                df_gps['diff'] = (df_gps['time'] - dt_foto).abs()
                ponto_proximo = df_gps.sort_values('diff').iloc[0]
                
                if ponto_proximo['diff'].total_seconds() < 30:
                    # Adiciona ao KML
                    pnt = kml.newpoint(name=foto_file.name)
                    pnt.coords = [(ponto_proximo['lon'], ponto_proximo['lat'])]
                    pnt.description = f"Foto tirada em: {dt_foto}\nSincronia GPS: {ponto_proximo['time']}"
                    encontrados += 1
            
            progress_bar.progress((i + 1) / len(fotos))

        st.write(f"✅ Sucesso: {encontrados} fotos georreferenciadas com precisão.")
        
        # Download do KML
        kml_output = kml.kml()
        st.download_button("📥 Baixar KML de Fotos", kml_output, "fotos_inspecao.kml")
