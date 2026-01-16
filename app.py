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

# CSS para interface profissional
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

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0)
area_min = st.sidebar.number_input("Área mínima (m²) - IBRAOP", value=7000.0)

st.sidebar.header("2. Restrições de Amostragem")
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50)
dist_min = st.sidebar.number_input("Distância mínima (m)", value=320.0)
recuo_curva = st.sidebar.number_input("Recuo em curvas (m)", value=150.0)

# Novo parâmetro de rigidez para garantir repetibilidade
sensibilidade = st.sidebar.number_input(
    "Rigidez na Curva (Graus)", 
    min_value=0.1, max_value=10.0, value=1.5, step=0.1,
    help="Define a deflexão angular. 1.5° a cada 20m é o padrão para evitar ruídos do KML."
)

# --- FUNÇÕES TÉCNICAS (ESTÁVEIS) ---
def identificar_zonas_curvas_estavel(linha, recuo, limite_graus):
    zonas = []
    extensao = linha.length
    passo = 20.0  # Amostragem fixa para garantir repetibilidade absoluta
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
    zonas.sort()
    unidas = []
    c_ini, c_fim = zonas[0]
    for i in range(1, len(zonas)):
        p_ini, p_fim = zonas[i]
        if p_ini <= c_fim: c_fim = max(c_fim, p_fim)
        else: unidas.append((c_ini, c_fim)); c_ini, c_fim = p_ini, p_fim
    unidas.append((c_ini, c_fim))
    return unidas

def gerar_pontos_finaos(linha, n_pontos, dist_min_m, zonas, largura_p, utm_crs):
    random.seed(42) # Semente fixa: mesmo arquivo + mesmos parâmetros = mesmos pontos sempre
    amostras_dists = []
    tentativas = 0
    while len(amostras_dists) < n_pontos and tentativas < 100000:
        d = random.uniform(0, linha.length)
        if not any(ini <= d <= fim for ini, fim in zonas):
            if all(abs(d - ja_tem) >= dist_min_m for ja_tem in amostras_dists):
                amostras_dists.append(d)
        tentativas += 1
    
    amostras_dists.sort()
    dados = []
    seq = ["Bordo Direito", "Eixo", "Bordo Esquerdo"]
    for i, dist in enumerate(amostras_dists):
        bordo = seq[i % 3]
        offset = (largura_p/2) if "Direito" in bordo else (-(largura_p/2) if "Esquerdo" in bordo else 0)
        p1, p2 = linha.interpolate(dist), linha.interpolate(dist + 0.1)
        mag = np.sqrt((p2.x-p1.x)**2 + (p2.y-p1.y)**2)
        geom = Point(p1.x - (p2.y-p1.y)/mag * offset, p1.y + (p2.x-p1.x)/mag * offset)
        p_wgs = gpd.GeoSeries([geom], crs=utm_crs).to_crs(epsg=4326)[0]
        dados.append({
            'ID': i + 1, 'Identificação': f"Amostra {i+1:02d}", 'Posição Lateral': bordo,
            'Quilometragem_m': dist, 'Quilometragem': f"km {dist/1000:.3f}",
            'Latitude': p_wgs.y, 'Longitude': p_wgs.x, 'geometry': geom, 'crs_origem': utm_crs
        })
    return pd.DataFrame(dados)

# --- LÓGICA PRINCIPAL ---
if uploaded_file:
    uploaded_file.seek(0)
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    # Cálculo Determinístico de Capacidade
    zonas_c = identificar_zonas_curvas_estavel(linha_rodovia, recuo_curva, sensibilidade)
    ext_util = max(0, linha_rodovia.length - sum([(f - i) for i, f in zonas_c]))
    capacidade_max = int(ext_util // dist_min) if ext_util > 0 else 0

    st.info(f"📏 **Dados:** {linha_rodovia.length/1000:.2f} km total | **Útil:** {ext_util/1000:.2f} km | **Capacidade:** {capacidade_max} amostras")

    # Geração
    if st.session_state['df_amostras'] is None:
        if qtd_desejada > capacidade_max:
            st.error(f"🚨 Capacidade excedida. Máximo possível para estes parâmetros: {capacidade_max} amostras.")
        else:
            n_alvo = None
            if qtd_desejada < n_min_ibraop:
                st.warning(f"⚠️ Abaixo do IBRAOP ({n_min_ibraop}).")
                c1, c2 = st.columns(2)
                if c1.button(f"Gerar Mínimo ({n_min_ibraop})"): n_alvo = n_min_ibraop
                if c2.button(f"Manter {qtd_desejada}"): n_alvo = qtd_desejada
            elif st.sidebar.button("Gerar Amostras"):
                n_alvo = qtd_desejada

            if n_alvo:
                st.session_state['df_amostras'] = gerar_pontos_finaos(linha_rodovia, n_alvo, dist_min, zonas_c, largura, utm_gdf.crs.to_string())
                st.rerun()

    # --- MAPA E RESULTADOS ---
    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        
        if st.session_state['map_center'] is None:
            st.session_state['map_center'] = [df.Latitude.mean(), df.Longitude.mean()]

        st.subheader("🗺️ Ajuste Geográfico")
        col_map, col_ctrl = st.columns([3, 1])

        with col_ctrl:
            id_para_editar = st.selectbox("ID para mover:", [None] + df['ID'].tolist())
            if id_para_editar:
                st.info("1. Clique no novo local no mapa.\n2. Clique em Confirmar.")
                confirmar = st.button("✅ Confirmar Nova Posição")
                if st.button("🔍 Centralizar na Amostra"):
                    ponto = df[df['ID'] == id_para_editar].iloc[0]
                    st.session_state['map_center'] = [ponto.Latitude, ponto.Longitude]
                    st.rerun()
            st.write("---")
            if st.sidebar.button("🗑️ Resetar Tudo"):
                st.session_state['df_amostras'] = None
                st.session_state['map_center'] = None
                st.rerun()

        with col_map:
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
                    tooltip=f"ID {row['ID']} - {row['Posição Lateral']}"
                ).add_to(m)

            mapa_res = st_folium(m, width=900, height=500, key="mapa_final_v8", returned_objects=["last_clicked"])

            # Lógica de Edição do Código Antigo (Restaurada)
            if id_para_editar and confirmar and mapa_res.get("last_clicked"):
                nl, no = mapa_res["last_clicked"]["lat"], mapa_res["last_clicked"]["lng"]
                idx = df.index[df['ID'] == id_para_editar][0]
                nova_g_utm = gpd.GeoSeries([Point(no, nl)], crs="EPSG:4326").to_crs(df.iloc[0].crs_origem)[0]
                nova_d = linha_rodovia.project(nova_g_utm)
                
                df.at[idx, 'Latitude'], df.at[idx, 'Longitude'] = nl, no
                df.at[idx, 'geometry'], df.at[idx, 'Quilometragem_m'] = nova_g_utm, nova_d
                df.at[idx, 'Quilometragem'] = f"km {nova_d/1000:.3f}"
                
                st.session_state['map_center'] = [nl, no]
                st.session_state['df_amostras'] = df
                st.rerun()

        st.subheader("📋 Tabela e Exportação")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)

        c1, c2 = st.columns(2)
        try:
            crs_orig = df['crs_origem'].iloc[0]
            amostras_gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs_orig).to_crs(epsg=4326)
            amostras_gdf['Name'] = amostras_gdf['Identificação']
            
            # KML
            buf_kml = io.BytesIO()
            amostras_gdf[['Name', 'geometry']].to_file(buf_kml, driver='KML')
            c1.download_button("📥 Baixar KML", buf_kml.getvalue(), "amostras_auditoria.kml")
            
            # Excel
            buf_xlsx = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx) as w:
                df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']).to_excel(w, index=False)
            c2.download_button("📥 Baixar Excel", buf_xlsx.getvalue(), "amostras_auditoria.xlsx")
        except: pass
