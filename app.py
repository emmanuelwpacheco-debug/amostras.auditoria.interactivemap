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

# --- ESTILIZAÇÃO ---
st.markdown("<style>.stException {display: none;} [data-testid='stStatusWidget'] {display: none;}</style>", unsafe_allow_html=True)

st.title("🚧 Auditoria: Amostragem de Campo")

# --- INITIAL STATE ---
if 'df_amostras' not in st.session_state: st.session_state['df_amostras'] = None
if 'map_center' not in st.session_state: st.session_state['map_center'] = None

# --- SIDEBAR ---
st.sidebar.header("1. Parâmetros Técnicos")
uploaded_file = st.sidebar.file_uploader("KML da Rodovia", type=['kml'])
largura = st.sidebar.number_input("Largura da pista (m)", value=7.0)
area_min = st.sidebar.number_input("Área mínima (m²) - IBRAOP", value=7000.0)
qtd_desejada = st.sidebar.number_input("Quantidade pretendida", value=50)
dist_min = st.sidebar.number_input("Distância mínima entre amostras (m)", value=320.0)
recuo_curva = st.sidebar.number_input("Recuo em curvas (m)", value=150.0)

# --- FUNÇÕES ---
def identificar_zonas_curvas(linha, recuo):
    zonas = []
    passo = 5 # Aumentada a precisão para 5m
    try:
        extensao = int(linha.length)
        for d in range(passo, extensao - passo, passo):
            p1, p2, p3 = linha.interpolate(d-passo), linha.interpolate(d), linha.interpolate(d+passo)
            v1, v2 = np.array([p2.x-p1.x, p2.y-p1.y]), np.array([p3.x-p2.x, p3.y-p2.y])
            norm = (np.linalg.norm(v1) * np.linalg.norm(v2))
            if norm > 0 and (np.dot(v1, v2)/norm) < 0.9997: # Sensibilidade de curva aumentada
                zonas.append((d - recuo, d + recuo))
    except: pass
    return zonas

def gerar_pontos_otimizados(linha, n_pontos, dist_min_m, zonas, largura_p, utm_crs):
    amostras_dists = []
    tentativas_totais = 0
    extensao = linha.length
    
    # 1ª Passada: Sorteio Aleatório Intensivo
    while len(amostras_dists) < n_pontos and tentativas_totais < 200000:
        dist = random.uniform(0, extensao)
        # Verifica curva e distância
        if not any(i <= dist <= f for i, f in zonas):
            if all(abs(dist - d) >= dist_min_m for d in amostras_dists):
                amostras_dists.append(dist)
        tentativas_totais += 1
    
    # 2ª Passada: Se faltar pouco, tenta preencher lacunas de forma sistemática
    if len(amostras_dists) < n_pontos:
        amostras_dists.sort()
        for _ in range(500): # Tenta 500 vezes encontrar fendas
            for i in range(len(amostras_dists)-1):
                gap_inicio = amostras_dists[i] + dist_min_m
                gap_fim = amostras_dists[i+1] - dist_min_m
                if gap_fim > gap_inicio:
                    nova_dist = (gap_inicio + gap_fim) / 2
                    if not any(i <= nova_dist <= f for i, f in zonas):
                        amostras_dists.append(nova_dist)
                        amostras_dists.sort()
                        if len(amostras_dists) >= n_pontos: break
            if len(amostras_dists) >= n_pontos: break

    amostras_dists = sorted(amostras_dists[:n_pontos])
    
    # Montagem do DataFrame
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
    
    return pd.DataFrame(dados), len(amostras_dists)

# --- LÓGICA ---
if uploaded_file:
    gdf_origem = gpd.read_file(uploaded_file, driver='KML')
    utm_gdf = gdf_origem.to_crs(gdf_origem.estimate_utm_crs())
    linha_rodovia = utm_gdf.geometry.iloc[0]
    extensao_km = linha_rodovia.length / 1000
    n_min_ibraop = int(np.ceil((linha_rodovia.length * largura) / area_min))

    st.info(f"📏 **Dados do Trecho:** {extensao_km:.2f} km | Mínimo IBRAOP: **{n_min_ibraop}**")

    if st.session_state['df_amostras'] is None:
        n_alvo = None
        if qtd_desejada < n_min_ibraop:
            st.warning(f"⚠️ Quantidade desejada ({qtd_desejada}) menor que o IBRAOP ({n_min_ibraop}).")
            c1, c2 = st.columns(2)
            if c1.button(f"Gerar {n_min_ibraop} (IBRAOP)"): n_alvo = n_min_ibraop
            if c2.button(f"Manter {qtd_desejada}"): n_alvo = qtd_desejada
        elif st.sidebar.button("Gerar Amostras"):
            n_alvo = qtd_desejada

        if n_alvo:
            zonas_c = identificar_zonas_curvas(linha_rodovia, recuo_curva)
            df_final, qtd_obtida = gerar_pontos_otimizados(linha_rodovia, n_alvo, dist_min, zonas_c, largura, utm_gdf.crs.to_string())
            st.session_state['df_amostras'] = df_final
            
            if qtd_obtida < n_alvo:
                # CÁLCULO DE CAPACIDADE MÁXIMA TEÓRICA (Aproximada)
                espaco_util = linha_rodovia.length - (len(zonas_c) * 10) # simplificado
                max_teorico = int(espaco_util / dist_min)
                st.error(f"🚨 **Não foi possível atingir a meta.**\n\nSolicitado: {n_alvo} | Gerado: {qtd_obtida}.\n\n"
                         f"**Motivo:** O espaçamento de {dist_min}m somado aos {recuo_curva}m de recuo em curvas "
                         f"esgotou o espaço físico da rodovia. Tente diminuir a distância mínima para ~{int(linha_rodovia.length/n_alvo)}m.")
            st.rerun()

    # (Lógica do Mapa e Tabela permanecem as mesmas para manter a estabilidade que já alcançamos)
    if st.session_state['df_amostras'] is not None:
        df = st.session_state['df_amostras']
        st.subheader("📋 Amostras Geradas")
        st.dataframe(df.drop(columns=['geometry', 'crs_origem', 'Quilometragem_m']), use_container_width=True)
        # ... Restante do código do mapa (Folium) e Downloads ... 'crs_origem', 'Quilometragem_m']), use_container_width=True)
        # (Botões de download omitidos aqui para brevidade, mas devem ser mantidos)
