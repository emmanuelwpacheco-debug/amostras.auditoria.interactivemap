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

fiona.drvsupport.supported_drivers['KML'] = 'rw'

st.set_page_config(page_title="Auditoria Rodoviária Pro", layout="wide")

st.title("🚧 Auditoria: Amostragem com Edição Manual")
st.markdown("Gere as amostras e, se necessário, **clique no mapa para reposicionar** o ponto selecionado.")

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura (m)", value=7.0)
area_min = st.sidebar.number_input("Área mín (m²)", value=7000.0)
qtd_desejada = st.sidebar.number_input("Qtd pretendida", value=50)
dist_min = st.sidebar.number_input("Dist. mín (m)", value=320.0)

# --- FUNÇÕES ---
def identificar_zonas_curvas(linha, recuo=150):
    zonas = []
    passo = 10
    try:
        for d in range(passo, int(linha.length) - passo, passo):
            p1, p2, p3 = linha.interpolate(d-passo), linha.interpolate(d), linha.interpolate(d+passo)
            v1 = np.array([p2.x-p1.x, p2.y-p1.y])
            v2 = np.array([p3.x-p2.x, p3.y-p2.y])
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
        if not any(i <= dist <= f for i, f in zonas):
            if all(abs(dist - a['dist']) >= dist_min_m for a in amostras):
                amostras.append({'dist': dist})
        tentativas += 1
    amostras.sort(key=lambda x: x['dist'])
    
    dados = []
    seq = ["Bordo Direito", "Eixo", "Bordo Esquerdo"]
    for i, amos in enumerate(amostras):
        bordo = seq[i % 3]
        offset = (largura_p/2) if bordo == "Bordo Direito" else (-(largura_p/2) if bordo == "Bordo Esquerdo" else 0)
        p1 = linha.interpolate(amos['dist'])
        p2 = linha.interpolate(amos['dist'] + 0.1)
        mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
        geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
        p_wgs = gpd.GeoSeries([geom], crs=utm_crs).to_crs(epsg=4326)[0]
        dados.append({
            'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}",
            'Posição Lateral': bordo, 'Quilometragem': amos['dist'],
            'Latitude': p_wgs.y, 'Longitude': p_wgs.x, 
            'geometry': geom
        })
    return pd.DataFrame(dados)

# --- LÓGICA ---
if uploaded_file:
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    # Botão de geração inicial
    if st.sidebar.button("♻️ Reiniciar/Gerar Amostras"):
        st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, qtd_desejada, dist_min, identificar_zonas_curvas(linha_rodovia), largura, utm_gdf.crs)
        st.session_state['ponto_selecionado'] = 1

    if 'df_amostras' in st.session_state and st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']

        col_tabela, col_mapa = st.columns([1, 2])

        with col_tabela:
            st.subheader("📍 Ajuste de Ponto")
            idx_selecionado = st.selectbox("Selecione a amostra para mover:", df['ID'].tolist(), index=int(st.session_state.get('ponto_selecionado', 1))-1)
            st.session_state['ponto_selecionado'] = idx_selecionado
            
            st.info("💡 **Como mover:** Selecione o ID acima e **clique no novo local** desejado no mapa ao lado.")
            
            st.write("---")
            st.dataframe(df[['Identificação', 'Posição Lateral', 'Latitude', 'Longitude']], height=400)

        with col_mapa:
            m = folium.Map(location=[df.Latitude.mean(), df.Longitude.mean()], zoom_start=15)
            folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
            
            # Desenha a linha da rodovia para referência
            rodovia_wgs84 = utm_gdf.to_crs(epsg=4326).geometry.iloc[0]
            folium.PolyLine(locations=[(p[1], p[0]) for p in rodovia_wgs84.coords], color="yellow", weight=2, opacity=0.5).add_to(m)

            for _, row in df.iterrows():
                is_active = (row['ID'] == idx_selecionado)
                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=8 if is_active else 5,
                    color="yellow" if is_active else "white",
                    fill=True,
                    fill_color="red" if row['Posição Lateral']=="Bordo Direito" else ("green" if row['Posição Lateral']=="Bordo Esquerdo" else "blue"),
                    fill_opacity=0.9,
                    popup=row['Identificação']
                ).add_to(m)

            # Captura o clique no mapa
            mapa_click = st_folium(m, width=800, height=600)

            # Lógica de atualização ao clicar
            if mapa_click and mapa_click.get("last_clicked"):
                new_lat = mapa_click["last_clicked"]["lat"]
                new_lon = mapa_click["last_clicked"]["lng"]
                
                # Atualiza o DataFrame na memória
                idx_no_df = df.index[df['ID'] == idx_selecionado][0]
                
                # Calcula nova geometria UTM para salvar corretamente
                nova_geom_wgs = Point(new_lon, new_lat)
                nova_geom_utm = gpd.GeoSeries([nova_geom_wgs], crs="EPSG:4326").to_crs(utm_gdf.crs)[0]
                
                # Calcula nova quilometragem (projeção na linha)
                nova_dist = linha_rodovia.project(nova_geom_utm)
                
                df.at[idx_no_df, 'Latitude'] = new_lat
                df.at[idx_no_df, 'Longitude'] = new_lon
                df.at[idx_no_df, 'geometry'] = nova_geom_utm
                df.at[idx_no_df, 'Quilometragem'] = nova_dist
                
                st.session_state['df_amostras'] = df
                st.rerun()

        # Botões de Download
        c1, c2 = st.columns(2)
        # Preparação do KML e Excel igual às versões anteriores...
        # (Omitido aqui por brevidade, mas deve-se usar o df atualizado do session_state)
