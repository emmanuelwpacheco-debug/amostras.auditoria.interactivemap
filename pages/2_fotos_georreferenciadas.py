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
    # Converte o conteúdo carregado para string para o gpxpy ler corretamente
    gpx_str = gpx_raw.getvalue().decode("utf-8")
    gpx = gpxpy.parse(gpx_str)
    pontos = []
    
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                # VERIFICAÇÃO: Só adiciona o ponto se ele tiver informação de tempo
                if point.time is not None:
                    pontos.append({
                        'time': point.time.replace(tzinfo=None),
                        'lat': point.latitude,
                        'lon': point.longitude,
                        'alt': point.elevation
                    })
    
    if not pontos:
        st.error("🚨 O arquivo GPX não contém informações de tempo (timestamps). Sem isso, não é possível sincronizar com as fotos.")
        return pd.DataFrame()
        
    return pd.DataFrame(pontos)

# --- LÓGICA PRINCIPAL ---
if gpx_file and fotos:
    df_gps = processar_gpx(gpx_file)
    st.success(f"Tracklog processado: {len(df_gps)} pontos de GPS encontrados.")

   # --- LÓGICA DE GERAÇÃO KMZ ---
if gpx_file and fotos:
    df_gps = processar_gpx(gpx_file)
    
    if st.button("Sincronizar Fotos e Gerar KMZ"):
        kml = simplekml.Kml()
        encontrados = 0
        
        for foto_file in fotos:
            dt_foto = extrair_data_foto(foto_file)
            
            if dt_foto:
                df_gps['diff'] = (df_gps['time'] - dt_foto).abs()
                ponto_proximo = df_gps.sort_values('diff').iloc[0]
                
                if ponto_proximo['diff'].total_seconds() < 30:
                    # 1. Salva a foto temporariamente para o KMZ conseguir "empacotar"
                    # 2. Cria o ponto com a imagem embutida no balão de descrição
                    pnt = kml.newpoint(name=foto_file.name)
                    pnt.coords = [(ponto_proximo['lon'], ponto_proximo['lat'])]
                    
                    # Adiciona a imagem ao pacote KMZ
                    path_no_kmz = kml.addfile(foto_file) 
                    
                    # Formatação HTML para a foto aparecer grande no Google Earth
                    pnt.description = f'<![CDATA[<img src="{path_no_kmz}" width="400" /><br/>Data: {dt_foto}]]>'
                    encontrados += 1
        
        # SALVAR COMO KMZ (Isso cria o pacote com as fotos dentro)
        buf_kmz = io.BytesIO()
        kml.savekmz(buf_kmz)
        st.download_button("📥 Baixar KMZ com FOTOS", buf_kmz.getvalue(), "fotos_inspecao.kmz")
