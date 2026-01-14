import streamlit as st
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point
import fiona
import random
import io
import folium
from streamlit_folium import st_folium

# Configuração de drivers KML
fiona.drvsupport.supported_drivers['KML'] = 'rw'

st.set_page_config(page_title="Auditoria Rodoviária Pro", layout="wide")

st.title("🚧 Auditoria: Amostragem de Campo")

# --- INICIALIZAÇÃO DO ESTADO ---
if 'map_center' not in st.session_state:
    st.session_state['map_center'] = None
if 'map_zoom' not in st.session_state:
    st.session_state['map_zoom'] = 14
if 'id_editando' not in st.session_state:
    st.session_state['id_editando'] = None
if 'df_amostras' not in st.session_state:
    st.session_state['df_amostras'] = None

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("Carregue o KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0, step=0.5)
area_min = st.sidebar.number_input("Área mínima por amostra (m²) - IBRAOP", value=7000.0, step=100.0)
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50, step=1)
dist_min = st.sidebar.number_input("Distância mínima (m)", value=320.0, step=10.0)

# --- FUNÇÕES ---
def identificar_zonas_curvas(linha, recuo=150):
    zonas = []
    passo = 10
    try:
        for d in range(passo, int(linha.length) - passo, passo):
            p1, p2, p3 = linha.interpolate(d-passo), linha.interpolate(d), linha.interpolate(d+passo)
            v1, v2 = np.array([p2.x-p1.x, p2.y-p1.y]), np.array([p3.x-p2.x, p3.y-p2.y])
            norm = (np.linalg.norm(v1) * np.linalg.norm(v2))
            if norm != 0 and (np.dot(v1, v2)/norm) < 0.9995:
                zonas.append((d - recuo, d + recuo))
    except: pass
    return zonas

def gerar_pontos_iniciais(linha, n_pontos, dist_min_m, zonas, largura_p, utm_crs):
    amostras = []
    tentativas = 0
    ext = linha.length
    while len(amostras) < n_pontos and tentativas < 50000:
        dist = random.uniform(0, ext)
        if not any(i <= dist <= f for i, f in zonas) and all(abs(dist - a['dist']) >= dist_min_m for a in amostras):
            amostras.append({'dist': dist})
        tentativas += 1
    amostras.sort(key=lambda x: x['dist'])
    dados = []
    seq = ["Bordo Direito", "Eixo", "Bordo Esquerdo"]
    for i, amos in enumerate(amostras):
        bordo = seq[i % 3]
        offset = (largura_p/2) if bordo == "Bordo Direito" else (-(largura_p/2) if bordo == "Bordo Esquerdo" else 0)
        p1, p2 = linha.interpolate(amos['dist']), linha.interpolate(amos['dist'] + 0.1)
        mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
        geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
        p_wgs = gpd.GeoSeries([geom], crs=utm_crs).to_crs(epsg=4326)[0]
        dados.append({
            'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}", 'Posição Lateral': bordo,
            'Quilometragem_m': amos['dist'], 'Quilometragem': f"km {amos['dist']/1000:.3f}",
            'Latitude': p_wgs.y, 'Longitude': p_wgs.x, 'geometry': geom, 'crs_origem': utm_crs
        })
    return pd.DataFrame(dados)

# --- LÓGICA PRINCIPAL ---
if uploaded_file:
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    st.info(f"📏 **Dados do Trecho:** Extensão: {linha_rodovia.length/1000:.2f} km | Mínimo IBRAOP: **{n_min_ibraop} amostras**")

    # Alerta IBRAOP
    if st.session_state['df_amostras'] is None:
        if qtd_desejada < n_min_ibraop:
            st.warning(f"⚠️ Quantidade solicitada ({qtd_desejada}) inferior ao IBRAOP ({n_min_ibraop}).")
            c_alt1, c_alt2 = st.columns(2)
            if c_alt1.button(f"Corrigir p/ {n_min_ibraop}"): 
                st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, n_min_ibraop, dist_min, identificar_zonas_curvas(linha_rodovia), largura, utm_gdf.crs.to_string())
                st.rerun()
            if c_alt2.button(f"Manter {qtd_desejada}"): 
                st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, qtd_desejada, dist_min, identificar_zonas_curvas(linha_rodovia), largura, utm_gdf.crs.to_string())
                st.rerun()
        elif st.sidebar.button("Gerar Amostras"):
            st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, qtd_desejada, dist_min, identificar_zonas_curvas(linha_rodovia), largura, utm_gdf.crs.to_string())
            st.rerun()

    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        id_edit = st.session_state['id_editando']

        # Cabeçalho de Ajuste
        st.subheader("🗺️ Ajuste Geográfico")
        if id_edit:
            st.success(f"📍 **Modo de Edição Ativo:** Clique no mapa para mover a **{df.loc[df['ID']==id_edit, 'Identificação'].values[0]}**")
            if st.button("Cancelar Seleção"):
                st.session_state['id_editando'] = None
                st.rerun()
        else:
            st.info("👆 **Dica:** Clique em um ponto no mapa para selecioná-lo para ajuste.")

        # Configuração do Mapa com Memória de Estado
        if st.session_state['map_center'] is None:
            st.session_state['map_center'] = [df.Latitude.mean(), df.Longitude.mean()]

        m = folium.Map(
            location=st.session_state['map_center'], 
            zoom_start=st.session_state['map_zoom']
        )
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
        
        cores = {"Bordo Direito": "red", "Eixo": "blue", "Bordo Esquerdo": "green"}
        for _, row in df.iterrows():
            folium.CircleMarker(
                location=[row['Latitude'], row['Longitude']],
                radius=10 if row['ID'] == id_edit else 7,
                color="yellow" if row['ID'] == id_edit else "white",
                fill=True, fill_color=cores[row['Posição Lateral']], fill_opacity=0.9,
                tooltip=f"{row['Identificação']}",
                popup=folium.Popup(f"Amostra {row['ID']}", parse_html=True)
            ).add_to(m)

        # Renderização do Mapa
        mapa_output = st_folium(
            m, 
            width=1100, 
            height=550, 
            key="mapa_rodovia",
            returned_objects=["last_object_clicked", "last_clicked", "zoom", "center"]
        )

        # Lógica de Sincronização e Edição
        if mapa_output:
            # Sincroniza zoom e centro SEMpre (evita o "pulo" ao interagir)
            st.session_state['map_zoom'] = mapa_output['zoom']
            st.session_state['map_center'] = [mapa_output['center']['lat'], mapa_output['center']['lng']]

            # Selecionar Ponto
            if mapa_output.get("last_object_clicked") and id_edit is None:
                click_lat = mapa_output["last_object_clicked"]["lat"]
                click_lon = mapa_output["last_object_clicked"]["lng"]
                # Encontra o ponto mais próximo do clique
                dists = np.sqrt((df.Latitude - click_lat)**2 + (df.Longitude - click_lon)**2)
                st.session_state['id_editando'] = int(df.loc[dists.idxmin(), 'ID'])
                st.rerun()

            # Mover Ponto Selecionado
            if id_edit and mapa_output.get("last_clicked"):
                new_lat = mapa_output["last_clicked"]["lat"]
                new_lon = mapa_output["last_clicked"]["lng"]
                
                idx = df.index[df['ID'] == id_edit][0]
                nova_geom_utm = gpd.GeoSeries([Point(new_lon, new_lat)], crs="EPSG:4326").to_crs(utm_gdf.crs)[0]
                nova_dist = linha_rodovia.project(nova_geom_utm)
                
                df.at[idx, 'Latitude'] = new_lat
                df.at[idx, 'Longitude'] = new_lon
                df.at[idx, 'geometry'] = nova_geom_utm
                df.at[idx, 'Quilometragem_m'] = nova_dist
                df.at[idx, 'Quilometragem'] = f"km {nova_dist/1000:.3f}"
                
                st.session_state['df_amostras'] = df
                st.session_state['id_editando'] = None # Fecha modo edição
                st.rerun()

        # Tabela e Downloads
        st.subheader("📋 Tabela de Amostras")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)

        c1, c2 = st.columns(2)
        try:
            crs_orig = df['crs_origem'].iloc[0]
            amostras_gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs_orig).to_crs(epsg=4326)
            amostras_gdf['Name'] = amostras_gdf['Identificação']
            buf_kml = io.BytesIO()
            amostras_gdf[['Name', 'geometry']].to_file(buf_kml, driver='KML')
            c1.download_button("📥 Baixar KML", buf_kml.getvalue(), "amostras.kml")
            
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx) as w:
                df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']).to_excel(w, index=False)
            c2.download_button("📥 Baixar Excel", buf_xlsx.getvalue(), "amostras.xlsx")
        except: pass
