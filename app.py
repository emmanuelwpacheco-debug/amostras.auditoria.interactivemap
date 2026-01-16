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

# CSS para interface estável
st.markdown("<style>.stException {display: none;} [data-testid='stStatusWidget'] {display: none;}</style>", unsafe_allow_html=True)
st.title("🚧 Auditoria: Amostragem de Campo")

# --- INICIALIZAÇÃO DE ESTADO ---
if 'df_amostras' not in st.session_state: st.session_state['df_amostras'] = None
if 'map_center' not in st.session_state: st.session_state['map_center'] = None
if 'map_zoom' not in st.session_state: st.session_state['map_zoom'] = 16

# --- SIDEBAR ---
st.sidebar.header("1. Arquivo e Geometria")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0)
area_min = st.sidebar.number_input("Área mínima (m²) - IBRAOP", value=7000.0)

st.sidebar.header("2. Restrições Técnicas")
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50)
dist_min = st.sidebar.number_input("Distância mínima (m)", value=320.0)
recuo_curva = st.sidebar.number_input("Recuo em curvas (m)", value=150.0)

# Sensibilidade em graus para repetibilidade absoluta
sensibilidade = st.sidebar.number_input(
    "Rigidez na Curva (Graus)", 
    min_value=0.1, max_value=10.0, value=1.5, step=0.1,
    help="Define a deflexão angular. 1.5° a cada 20m é um padrão estável para curvas reais."
)

# --- FUNÇÃO TÉCNICA DETERMINÍSTICA ---
def identificar_zonas_curvas_estavel(linha, recuo, limite_graus):
    zonas = []
    extensao = linha.length
    passo = 20.0 
    distancias = np.arange(0, extensao, passo)
    if len(distancias) < 3: return []

    for d in range(1, len(distancias) - 1):
        p1, p2, p3 = linha.interpolate(distancias[d-1]), linha.interpolate(distancias[d]), linha.interpolate(distancias[d+1])
        v1, v2 = np.array([p2.x - p1.x, p2.y - p1.y]), np.array([p3.x - p2.x, p3.y - p2.y])
        normas = np.linalg.norm(v1) * np.linalg.norm(v2)
        if normas > 0:
            cos_theta = np.clip(np.dot(v1, v2) / normas, -1.0, 1.0)
            if np.degrees(np.arccos(cos_theta)) > limite_graus:
                zonas.append((max(0, distancias[d] - recuo), min(extensao, distancias[d] + recuo)))
    
    if not zonas: return []
    zonas.sort(); unidas = []
    c_ini, c_fim = zonas[0]
    for i in range(1, len(zonas)):
        p_ini, p_fim = zonas[i]
        if p_ini <= c_fim: c_fim = max(c_fim, p_fim)
        else: unidas.append((c_ini, c_fim)); c_ini, c_fim = p_ini, p_fim
    unidas.append((c_ini, c_fim))
    return unidas

# --- LÓGICA DE PROCESSAMENTO ---
if uploaded_file:
    uploaded_file.seek(0)
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    # Análise estável
    zonas_c = identificar_zonas_curvas_estavel(linha_rodovia, recuo_curva, sensibilidade)
    ext_util = max(0, linha_rodovia.length - sum([(f - i) for i, f in zonas_c]))
    capacidade_max = int(ext_util // dist_min) if ext_util > 0 else 0

    st.info(f"📏 **Status:** {linha_rodovia.length/1000:.2f} km total | **Útil:** {ext_util/1000:.2f} km | **Capacidade Máxima:** {capacidade_max}")

    # GERAÇÃO
    if st.session_state['df_amostras'] is None:
        if qtd_desejada > capacidade_max:
            st.error(f"🚨 Capacidade excedida. O trecho suporta no máximo {capacidade_max} amostras.")
        else:
            if st.sidebar.button("Gerar Amostras"):
                random.seed(42) # Semente fixa para repetibilidade
                amostras_dists = []
                for _ in range(100000):
                    if len(amostras_dists) >= qtd_desejada: break
                    d = random.uniform(0, linha_rodovia.length)
                    if not any(ini <= d <= fim for ini, fim in zonas_c):
                        if all(abs(d - j) >= dist_min for j in amostras_dists):
                            amostras_dists.append(d)
                
                amostras_dists.sort()
                dados = []
                seq = ["Bordo Direito", "Eixo", "Bordo Esquerdo"]
                for i, d in enumerate(amostras_dists):
                    bordo = seq[i % 3]
                    offset = (largura/2) if "Direito" in bordo else (-(largura/2) if "Esquerdo" in bordo else 0)
                    p1, p2 = linha_rodovia.interpolate(d), linha_rodovia.interpolate(d + 0.1)
                    mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
                    geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
                    p_wgs = gpd.GeoSeries([geom], crs=utm_gdf.crs).to_crs(epsg=4326)[0]
                    dados.append({
                        'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}", 'Posição Lateral': bordo,
                        'Quilometragem': f"km {d/1000:.3f}", 'Latitude': p_wgs.y, 'Longitude': p_wgs.x,
                        'geometry': geom, 'crs_origem': utm_gdf.crs.to_string(), 'km_m': d
                    })
                st.session_state['df_amostras'] = pd.DataFrame(dados)
                st.rerun()

    # MAPA E EDIÇÃO
    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        col_map, col_ctrl = st.columns([3, 1])

        with col_ctrl:
            id_para_editar = st.selectbox("Editar ID:", [None] + df['ID'].tolist())
            if id_para_editar:
                st.info("Clique no mapa e confirme.")
                confirmar = st.button("✅ Confirmar Nova Posição")
            if st.sidebar.button("🗑️ Resetar Tudo"):
                st.session_state['df_amostras'] = None
                st.rerun()

        with col_map:
            if st.session_state['map_center'] is None:
                st.session_state['map_center'] = [df.Latitude.mean(), df.Longitude.mean()]
            m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'])
            folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
            
            for _, r in df.iterrows():
                folium.CircleMarker(
                    location=[r.Latitude, r.Longitude], radius=8,
                    color="yellow" if r.ID == id_para_editar else "white",
                    fill=True, fill_color="blue" if r['Posição Lateral']=="Eixo" else ("red" if "Direito" in r['Posição Lateral'] else "green"),
                    fill_opacity=0.9
                ).add_to(m)

            mapa_res = st_folium(m, width=900, height=500, key="mapa_v7", returned_objects=["last_clicked"])

            if id_para_editar and confirmar and mapa_res.get("last_clicked"):
                nl, no = mapa_res["last_clicked"]["lat"], mapa_res["last_clicked"]["lng"]
                idx = df.index[df['ID'] == id_para_editar][0]
                g_utm = gpd.GeoSeries([Point(no, nl)], crs="EPSG:4326").to_crs(df.iloc[0].crs_origem)[0]
                d_m = linha_rodovia.project(g_utm)
                df.at[idx, 'Latitude'], df.at[idx, 'Longitude'] = nl, no
                df.at[idx, 'geometry'], df.at[idx, 'Quilometragem'] = g_utm, f"km {d_m/1000:.3f}"
                st.session_state['map_center'] = [nl, no]
                st.session_state['df_amostras'] = df
                st.rerun()

        # --- SEÇÃO DE DOWNLOADS ---
        st.subheader("📋 Resultados e Exportação")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'km_m']), use_container_width=True)

        c1, c2 = st.columns(2)
        try:
            # Gerar KML
            amostras_gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=df.iloc[0].crs_origem).to_crs(epsg=4326)
            amostras_gdf['Name'] = amostras_gdf['Identificação']
            buf_kml = io.BytesIO()
            amostras_gdf[['Name', 'geometry']].to_file(buf_kml, driver='KML')
            c1.download_button("📥 Baixar KML", buf_kml.getvalue(), "auditoria_amostras.kml")

            # Gerar Excel
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx) as w:
                df.drop(columns=['geometry', 'crs_origem', 'km_m']).to_excel(w, index=False)
            c2.download_button("📥 Baixar Excel", buf_xlsx.getvalue(), "auditoria_amostras.xlsx")
        except Exception as e:
            st.warning(f"Erro na exportação: {e}")
