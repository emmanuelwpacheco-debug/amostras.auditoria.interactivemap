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

# CSS para suavizar a interface e evitar flashes de erro
st.markdown("<style>.stException {display: none;} </style>", unsafe_allow_html=True)

st.title("🚧 Auditoria: Amostragem de Campo (Com Trava de Curvas)")

# --- INICIALIZAÇÃO DE ESTADO ---
if 'df_amostras' not in st.session_state:
    st.session_state['df_amostras'] = None
if 'id_editando' not in st.session_state:
    st.session_state['id_editando'] = None
if 'map_center' not in st.session_state:
    st.session_state['map_center'] = None
if 'map_zoom' not in st.session_state:
    st.session_state['map_zoom'] = 15

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0)
area_min = st.sidebar.number_input("Área mínima (m²) - IBRAOP", value=7000.0)
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50)
dist_min = st.sidebar.number_input("Distância mínima entre as amostras (m)", value=320.0)
recuo_curva = st.sidebar.number_input("Recuo de segurança em curvas (m)", value=150.0)

# --- FUNÇÕES TÉCNICAS ---
def identificar_zonas_curvas(linha, recuo):
    """Identifica trechos onde o raio de curvatura é acentuado."""
    zonas = []
    passo = 10
    try:
        extensao = int(linha.length)
        for d in range(passo, extensao - passo, passo):
            p1 = linha.interpolate(d - passo)
            p2 = linha.interpolate(d)
            p3 = linha.interpolate(d + passo)
            
            v1 = np.array([p2.x - p1.x, p2.y - p1.y])
            v2 = np.array([p3.x - p2.x, p3.y - p2.y])
            
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 > 0 and norm2 > 0:
                cos_theta = np.dot(v1, v2) / (norm1 * norm2)
                # Se o ângulo for maior que o limite (0.9995 = ~1.8 graus em 10m)
                if cos_theta < 0.9995:
                    zonas.append((d - recuo, d + recuo))
    except Exception as e:
        st.error(f"Erro na análise de geometria: {e}")
    return zonas

def gerar_pontos_iniciais(linha, n_pontos, dist_min_m, zonas_proibidas, largura_p, utm_crs):
    """Gera pontos respeitando distância mínima e zonas de curva."""
    amostras = []
    tentativas = 0
    ext = linha.length
    
    while len(amostras) < n_pontos and tentativas < 60000:
        dist = random.uniform(0, ext)
        
        # Verifica se está em curva
        em_curva = any(inicio <= dist <= fim for inicio, fim in zonas_proibidas)
        
        if not em_curva:
            # Verifica distância mínima entre pontos já existentes
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

    st.info(f"📏 **Dados:** Extensão: {linha_rodovia.length/1000:.2f} km | Mínimo IBRAOP: **{n_min_ibraop} amostras**")

    # Controle de Geração Inicial com Alerta Normativo
    if st.session_state['df_amostras'] is None:
        if qtd_desejada < n_min_ibraop:
            st.warning(f"⚠️ Quantidade inferior ao IBRAOP ({n_min_ibraop}).")
            c1, c2 = st.columns(2)
            if c1.button(f"Gerar Mínimo ({n_min_ibraop})"):
                zonas = identificar_zonas_curvas(linha_rodovia, recuo_curva)
                st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, n_min_ibraop, dist_min, zonas, largura, utm_gdf.crs.to_string())
                st.rerun()
            if c2.button(f"Prosseguir com {qtd_desejada}"):
                zonas = identificar_zonas_curvas(linha_rodovia, recuo_curva)
                st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, qtd_desejada, dist_min, zonas, largura, utm_gdf.crs.to_string())
                st.rerun()
        elif st.sidebar.button("Gerar Amostras"):
            zonas = identificar_zonas_curvas(linha_rodovia, recuo_curva)
            st.session_state['df_amostras'] = gerar_pontos_iniciais(linha_rodovia, qtd_desejada, dist_min, zonas, largura, utm_gdf.crs.to_string())
            st.rerun()

    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        
        st.subheader("🗺️ Ajuste Geográfico")
        col_map, col_ctrl = st.columns([3, 1])

        with col_ctrl:
            st.write("**Edição Manual**")
            id_para_editar = st.selectbox("ID para mover:", [None] + df['ID'].tolist(), 
                                          format_func=lambda x: f"Amostra {x}" if x else "Nenhum")
            st.session_state['id_editando'] = id_para_editar
            
            if id_para_editar:
                st.success("Clique no mapa para reposicionar.")
                if st.button("Limpar Seleção"):
                    st.session_state['id_editando'] = None
                    st.rerun()
            
            st.write("---")
            if st.sidebar.button("🗑️ Resetar Tudo"):
                st.session_state['df_amostras'] = None
                st.rerun()

        with col_map:
            if st.session_state['map_center'] is None:
                st.session_state['map_center'] = [df.Latitude.mean(), df.Longitude.mean()]

            m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'])
            folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
            
            # Legenda de cores
            cores = {"Bordo Direito": "red", "Eixo": "blue", "Bordo Esquerdo": "green"}
            
            for _, row in df.iterrows():
                is_ed = (row['ID'] == st.session_state['id_editando'])
                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=12 if is_ed else 7,
                    color="yellow" if is_ed else "white",
                    fill=True, fill_color=cores[row['Posição Lateral']], fill_opacity=0.9,
                    tooltip=f"ID {row['ID']}: {row['Posição Lateral']}"
                ).add_to(m)

            # Renderização estável
            mapa_res = st_folium(m, width=900, height=500, key="mapa_v4")

            if mapa_res:
                # Atualização de Zoom/Centro sem erro
                st.session_state['map_zoom'] = mapa_res.get('zoom', st.session_state['map_zoom'])
                st.session_state['map_center'] = [mapa_res['center']['lat'], mapa_res['center']['lng']]

                # Lógica de movimentação
                if st.session_state['id_editando'] and mapa_res.get("last_clicked"):
                    new_lat, new_lon = mapa_res["last_clicked"]["lat"], mapa_res["last_clicked"]["lng"]
                    idx = df.index[df['ID'] == st.session_state['id_editando']][0]
                    
                    # Projeta o novo ponto na rodovia para atualizar o KM corretamente
                    nova_geom_utm = gpd.GeoSeries([Point(new_lon, new_lat)], crs="EPSG:4326").to_crs(utm_gdf.crs)[0]
                    nova_dist = linha_rodovia.project(nova_geom_utm)
                    
                    df.at[idx, 'Latitude'], df.at[idx, 'Longitude'] = new_lat, new_lon
                    df.at[idx, 'geometry'], df.at[idx, 'Quilometragem_m'] = nova_geom_utm, nova_dist
                    df.at[idx, 'Quilometragem'] = f"km {nova_dist/1000:.3f}"
                    
                    st.session_state['df_amostras'] = df
                    st.session_state['id_editando'] = None
                    st.rerun()

        st.subheader("📋 Tabela Final")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)

        # Exportação
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
