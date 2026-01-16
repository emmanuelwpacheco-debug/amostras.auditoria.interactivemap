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

# CSS para esconder mensagens de processamento e flicker
st.markdown("""
    <style>
    .stException {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    </style>
    """, unsafe_allow_html=True)

st.title("🚧 Auditoria: Amostragem de Campo")

# --- INICIALIZAÇÃO DE ESTADO ---
if 'df_amostras' not in st.session_state: st.session_state['df_amostras'] = None
if 'map_center' not in st.session_state: st.session_state['map_center'] = None
if 'map_zoom' not in st.session_state: st.session_state['map_zoom'] = 16
if 'id_editando' not in st.session_state: st.session_state['id_editando'] = None

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0)
area_min = st.sidebar.number_input("Área mínima (m²) - IBRAOP", value=7000.0)
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50)
dist_min = st.sidebar.number_input("Distância mínima (m)", value=320.0)
recuo_curva = st.sidebar.number_input("Recuo em curvas (m)", value=150.0)

# --- FUNÇÕES TÉCNICAS ---
def identificar_zonas_curvas(linha, recuo):
    zonas = []
    passo = 10
    try:
        extensao = int(linha.length)
        for d in range(passo, extensao - passo, passo):
            p1, p2, p3 = linha.interpolate(d-passo), linha.interpolate(d), linha.interpolate(d+passo)
            v1, v2 = np.array([p2.x-p1.x, p2.y-p1.y]), np.array([p3.x-p2.x, p3.y-p2.y])
            norm = (np.linalg.norm(v1) * np.linalg.norm(v2))
            if norm > 0 and (np.dot(v1, v2)/norm) < 0.9995:
                zonas.append((d - recuo, d + recuo))
    except: pass
    return zonas

def gerar_pontos_robustos(linha, n_pontos, dist_min_m, zonas, largura_p, utm_crs):
    amostras_dists = []
    extensao = linha.length
    
    # 1. Tentativa Aleatória (Estocástica)
    for _ in range(100000):
        if len(amostras_dists) >= n_pontos: break
        dist = random.uniform(0, extensao)
        if not any(i <= dist <= f for i, f in zonas):
            if all(abs(dist - d) >= dist_min_m for d in amostras_dists):
                amostras_dists.append(dist)
    
    # 2. Preenchimento de Lacunas (Caso o aleatório falhe)
    if len(amostras_dists) < n_pontos:
        amostras_dists.sort()
        for _ in range(1000):
            if len(amostras_dists) >= n_pontos: break
            for i in range(len(amostras_dists)-1):
                gap = amostras_dists[i+1] - amostras_dists[i]
                if gap >= 2 * dist_min_m:
                    nova_pos = amostras_dists[i] + (gap / 2)
                    if not any(ini <= nova_pos <= fim for ini, fim in zonas):
                        amostras_dists.append(nova_pos)
                        amostras_dists.sort()
                        if len(amostras_dists) >= n_pontos: break

    amostras_dists.sort()
    qtd_real = len(amostras_dists)
    
    dados = []
    seq = ["Bordo Direito", "Eixo", "Bordo Esquerdo"]
    for i, dist in enumerate(amostras_dists):
        bordo = seq[i % 3]
        offset = (largura_p/2) if bordo == "Bordo Direito" else (-(largura_p/2) if bordo == "Bordo Esquerdo" else 0)
        p1, p2 = linha.interpolate(dist), linha.interpolate(dist + 0.1)
        mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
        geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
        p_wgs = gpd.GeoSeries([geom], crs=utm_crs).to_crs(epsg=4326)[0]
        dados.append({
            'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}", 'Posição Lateral': bordo,
            'Quilometragem_m': dist, 'Quilometragem': f"km {dist/1000:.3f}",
            'Latitude': p_wgs.y, 'Longitude': p_wgs.x, 'geometry': geom, 'crs_origem': utm_crs
        })
    return pd.DataFrame(dados), qtd_real

# --- LÓGICA DE INTERFACE ---
if uploaded_file:
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    st.info(f"📏 **Dados:** {linha_rodovia.length/1000:.2f} km | Mínimo IBRAOP: **{n_min_ibraop}**")

    # Botões de Geração com Alerta Pop-up
    if st.session_state['df_amostras'] is None:
        n_alvo = None
        if qtd_desejada < n_min_ibraop:
            st.warning(f"⚠️ Abaixo do IBRAOP ({n_min_ibraop}).")
            c1, c2 = st.columns(2)
            if c1.button(f"Gerar Mínimo ({n_min_ibraop})"): n_alvo = n_min_ibraop
            if c2.button(f"Manter {qtd_desejada}"): n_alvo = qtd_desejada
        elif st.sidebar.button("Gerar Amostras"):
            n_alvo = qtd_desejada

        if n_alvo:
            zonas = identificar_zonas_curvas(linha_rodovia, recuo_curva)
            df_g, qtd = gerar_pontos_robustos(linha_rodovia, n_alvo, dist_min, zonas, largura, utm_gdf.crs.to_string())
            st.session_state['df_amostras'] = df_g
            if qtd < n_alvo:
                st.toast(f"⚠️ Atenção! Apenas {qtd} amostras couberam no trecho.", icon="❌")
                st.error(f"As condições de contorno (distância de {dist_min}m) permitiram gerar apenas {qtd} de {n_alvo} amostras.")
            st.rerun()

    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        
        # --- PAINEL DE AJUSTE ---
        st.subheader("🗺️ Ajuste Geográfico")
        col_map, col_ctrl = st.columns([3, 1])

        with col_ctrl:
            id_para_editar = st.selectbox("ID para mover:", [None] + df['ID'].tolist())
            if id_para_editar:
                st.info("Clique no mapa e confirme abaixo.")
                confirmar = st.button("✅ Confirmar Nova Posição")
                if st.button("🔍 Ir para Amostra"):
                    ponto = df[df['ID'] == id_para_editar].iloc[0]
                    st.session_state['map_center'] = [ponto.Latitude, ponto.Longitude]
                    st.rerun()
            st.write("---")
            if st.sidebar.button("🗑️ Resetar Tudo"):
                st.session_state['df_amostras'] = None
                st.session_state['map_center'] = None
                st.rerun()

        with col_map:
            if st.session_state['map_center'] is None:
                st.session_state['map_center'] = [df.Latitude.mean(), df.Longitude.mean()]
            
            m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'])
            folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
            
            cores = {"Bordo Direito": "red", "Eixo": "blue", "Bordo Esquerdo": "green"}
            for _, row in df.iterrows():
                is_ed = (row['ID'] == id_para_editar)
                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=10 if is_ed else 7,
                    color="yellow" if is_ed else "white",
                    fill=True, fill_color=cores[row['Posição Lateral']], fill_opacity=0.9,
                    tooltip=f"ID {row['ID']}"
                ).add_to(m)

            # MAPA ESTÁVEL (Apenas retorna clique)
            mapa_res = st_folium(m, width=900, height=500, key="mapa_estavel", returned_objects=["last_clicked"])

            if id_para_editar and confirmar and mapa_res.get("last_clicked"):
                new_lat, new_lon = mapa_res["last_clicked"]["lat"], mapa_res["last_clicked"]["lng"]
                idx = df.index[df['ID'] == id_para_editar][0]
                nova_geom_utm = gpd.GeoSeries([Point(new_lon, new_lat)], crs="EPSG:4326").to_crs(utm_gdf.crs)[0]
                nova_dist = linha_rodovia.project(nova_geom_utm)
                
                df.at[idx, 'Latitude'], df.at[idx, 'Longitude'] = new_lat, new_lon
                df.at[idx, 'geometry'] = nova_geom_utm
                df.at[idx, 'Quilometragem'] = f"km {nova_dist/1000:.3f}"
                
                st.session_state['map_center'] = [new_lat, new_lon]
                st.session_state['df_amostras'] = df
                st.rerun()

        # --- TABELA E EXPORTAÇÃO ---
        st.subheader("📋 Resultados e Download")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)

        c1, c2 = st.columns(2)
        try:
            # Export KML
            crs_orig = df['crs_origem'].iloc[0]
            amostras_gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs_orig).to_crs(epsg=4326)
            amostras_gdf['Name'] = amostras_gdf['Identificação']
            buf_kml = io.BytesIO()
            amostras_gdf[['Name', 'geometry']].to_file(buf_kml, driver='KML')
            c1.download_button("📥 Baixar KML", buf_kml.getvalue(), "amostras.kml", "text/xml")
            
            # Export Excel
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx, engine='openpyxl') as writer:
                df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']).to_excel(writer, index=False)
            c2.download_button("📥 Baixar Excel", buf_xlsx.getvalue(), "amostras.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"Erro ao gerar arquivos: {e}")
