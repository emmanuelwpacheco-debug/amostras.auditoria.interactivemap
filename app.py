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

st.title("🚧 Auditoria: Amostragem com Edição Dinâmica")
st.markdown("Gere as amostras, visualize os pontos e reposicione-os clicando no mapa.")

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("Carregue o KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0, step=0.5)
area_min = st.sidebar.number_input("Área mínima por amostra (m²) - IBRAOP", value=7000.0, step=100.0)
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50, step=1)
dist_min = st.sidebar.number_input("Distância mínima entre pontos (m)", value=320.0, step=10.0)

# --- FUNÇÕES DE APOIO ---
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
        p1, p2 = linha.interpolate(amos['dist']), linha.interpolate(amos['dist'] + 0.1)
        mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
        geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
        p_wgs = gpd.GeoSeries([geom], crs=utm_crs).to_crs(epsg=4326)[0]
        dados.append({
            'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}",
            'Posição Lateral': bordo, 'Quilometragem_m': amos['dist'],
            'Quilometragem': f"km {amos['dist']/1000:.3f}",
            'Latitude': p_wgs.y, 'Longitude': p_wgs.x, 
            'geometry': geom, 'crs_origem': utm_crs
        })
    return pd.DataFrame(dados)

# --- LÓGICA PRINCIPAL ---
if uploaded_file:
    # Memorial de Cálculo e Informações do Trecho
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    extensao_total = linha_rodovia.length
    n_min_ibraop = int(np.ceil((extensao_total * largura) / area_min))

    st.info(f"📏 **Dados do Trecho:** Extensão: {extensao_total/1000:.2f} km | Mínimo IBRAOP: **{n_min_ibraop} amostras**")

    # Botão de geração inicial
    if st.sidebar.button("♻️ Gerar Novas Amostras"):
        zonas = identificar_zonas_curvas(linha_rodovia)
        n_pontos = max(qtd_desejada, n_min_ibraop) if qtd_desejada >= n_min_ibraop else qtd_desejada
        st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, n_pontos, dist_min, zonas, largura, utm_gdf.crs.to_string())

    if 'df_amostras' in st.session_state and st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']

        # Área de Edição
        with st.expander("🛠️ Painel de Ajuste Manual", expanded=True):
            col_edit1, col_edit2 = st.columns([1, 2])
            with col_edit1:
                idx_selecionado = st.selectbox("Selecione o ID para reposicionar:", df['ID'].tolist())
                st.write(f"Você está editando a **{df.loc[df['ID']==idx_selecionado, 'Identificação'].values[0]}**")
                st.caption("Ao clicar no mapa à direita, este ponto mudará para a nova posição.")
            
            with col_edit2:
                # Mapa Interativo
                m = folium.Map(location=[df.Latitude.mean(), df.Longitude.mean()], zoom_start=15)
                folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
                
                cores = {"Bordo Direito": "red", "Eixo": "blue", "Bordo Esquerdo": "green"}
                for _, row in df.iterrows():
                    is_active = (row['ID'] == idx_selecionado)
                    folium.CircleMarker(
                        location=[row['Latitude'], row['Longitude']],
                        radius=9 if is_active else 6,
                        color="yellow" if is_active else "white",
                        fill=True,
                        fill_color=cores[row['Posição Lateral']],
                        fill_opacity=0.9,
                        popup=f"ID: {row['ID']} | {row['Posição Lateral']}<br>{row['Quilometragem']}"
                    ).add_to(m)

                # Captura clique
                mapa_click = st_folium(m, width=700, height=450, key="mapa_edicao")

                if mapa_click and mapa_click.get("last_clicked"):
                    new_lat = mapa_click["last_clicked"]["lat"]
                    new_lon = mapa_click["last_clicked"]["lng"]
                    
                    idx_no_df = df.index[df['ID'] == idx_selecionado][0]
                    
                    # Recalcula geometria e KM
                    nova_geom_wgs = Point(new_lon, new_lat)
                    nova_geom_utm = gpd.GeoSeries([nova_geom_wgs], crs="EPSG:4326").to_crs(utm_gdf.crs)[0]
                    nova_dist = linha_rodovia.project(nova_geom_utm)
                    
                    df.at[idx_no_df, 'Latitude'] = new_lat
                    df.at[idx_no_df, 'Longitude'] = new_lon
                    df.at[idx_no_df, 'geometry'] = nova_geom_utm
                    df.at[idx_no_df, 'Quilometragem_m'] = nova_dist
                    df.at[idx_no_df, 'Quilometragem'] = f"km {nova_dist/1000:.3f}"
                    
                    st.session_state['df_amostras'] = df
                    st.rerun()

        # Tabela de Resultados
        st.subheader("📋 Tabela Final de Amostras")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)

        # Downloads
        c1, c2 = st.columns(2)
        try:
            crs_orig = df['crs_origem'].iloc[0]
            amostras_gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs_orig).to_crs(epsg=4326)
            amostras_gdf['Name'] = amostras_gdf['Identificação'] + " - " + amostras_gdf['Posição Lateral']
            buf_kml = io.BytesIO()
            amostras_gdf[['Name', 'geometry']].to_file(buf_kml, driver='KML')
            c1.download_button("📥 Baixar KML Atualizado", buf_kml.getvalue(), "amostras_revisadas.kml")
            
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx, engine='openpyxl') as writer:
                df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']).to_excel(writer, index=False)
            c2.download_button("📥 Baixar Excel Atualizado", buf_xlsx.getvalue(), "amostras_revisadas.xlsx")
        except: st.error("Erro na geração dos arquivos de saída.")
