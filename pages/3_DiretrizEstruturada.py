import streamlit as st
import pandas as pd
import pdfplumber
import simplekml
from pyproj import Transformer
import io
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Diretriz Estruturada", layout="wide")

# --- INICIALIZAÇÃO DO ESTADO ---
if 'df_projeto' not in st.session_state:
    st.session_state['df_projeto'] = None
if 'df_processado' not in st.session_state:
    st.session_state['df_processado'] = None

st.title("🛣️ Diretriz Estruturada com Mapa Interativo")

# --- SIDEBAR ---
st.sidebar.header("Configurações Geográficas")
uploaded_pdf = st.sidebar.file_uploader("Upload da Nota de Serviço (PDF)", type=['pdf'])
zona_utm = st.sidebar.number_input("Zona UTM", value=23)
hemisferio = st.sidebar.selectbox("Hemisfério", ["Sul", "Norte"])

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        total_pags = len(pdf.pages)
        p_ini, p_fim = st.sidebar.slider("Intervalo de páginas", 1, total_pags, (1, total_pags))
        
        if st.sidebar.button("🔍 Extrair Dados do PDF"):
            dados_acumulados = []
            for i in range(p_ini - 1, p_fim):
                page = pdf.pages[i]
                table = page.extract_table()
                if table:
                    temp_df = pd.DataFrame(table)
                    dados_acumulados.append(temp_df)
            
            if dados_acumulados:
                st.session_state['df_projeto'] = pd.concat(dados_acumulados, ignore_index=True)
                st.rerun()

# --- INTERFACE DE MAPEAMENTO E PROCESSAMENTO ---
if st.session_state['df_projeto'] is not None:
    df_raw = st.session_state['df_projeto']
    
    st.subheader("📍 Mapeamento de Colunas")
    cols_idx = list(range(len(df_raw.columns)))
    
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: idx_estaca = st.selectbox("Índice Estaca (+)", cols_idx, index=9)
    with c2: idx_norte = st.selectbox("Índice Norte (Y)", cols_idx, index=11)
    with c3: idx_leste = st.selectbox("Índice Leste (X)", cols_idx, index=12)
    with c4: idx_cter = st.selectbox("Índice Cota Terreno", cols_idx, index=13)
    with c5: idx_cproj = st.selectbox("Índice Cota Projeto", cols_idx, index=14)

    if st.button("🛰️ Processar e Visualizar no Mapa"):
        try:
            # Filtragem e Limpeza
            df_limpo = df_raw[df_raw[idx_norte].str.contains(r'\d', na=False)].copy()
            
            def limpar_num(val):
                if not val: return 0.0
                return float(str(val).replace('.', '').replace(',', '.'))

            srid = f"+proj=utm +zone={zona_utm} +{'south' if hemisferio == 'Sul' else 'north'} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            transformer = Transformer.from_crs(srid, "EPSG:4326")
            
            kml = simplekml.Kml()
            coords_para_kml = []
            lista_pontos_mapa = []

            for _, row in df_limpo.iterrows():
                n = limpar_num(row[idx_norte])
                l = limpar_num(row[idx_leste])
                z = limpar_num(row[idx_cproj])
                estaca = f"{row[idx_estaca-1]} + {row[idx_estaca]}"
                
                lat, lon = transformer.transform(l, n)
                coords_para_kml.append((lon, lat, z))
                
                # Dados para o Mapa Interativo
                lista_pontos_mapa.append({
                    'lat': lat, 'lon': lon, 'estaca': estaca, 'z': z, 'terreno': row[idx_cter]
                })
                
                # Adicionar Ponto ao KML
                pnt = kml.newpoint(name=f"Estaca {estaca}")
                pnt.coords = [(lon, lat, z)]
                pnt.altitudemode = simplekml.AltitudeMode.absolute
                pnt.description = f"Cota Projeto: {z}m\nCota Terreno: {row[idx_cter]}m"

            # --- AQUI ESTÁ A LINHA 3D ---
            lin = kml.newlinestring(name="Eixo da Rodovia (3D)")
            lin.coords = coords_para_kml
            lin.altitudemode = simplekml.AltitudeMode.absolute
            lin.style.linestyle.color = simplekml.Color.red # Vermelho
            lin.style.linestyle.width = 5
            
            # Guardar resultados no estado
            st.session_state['df_processado'] = pd.DataFrame(lista_pontos_mapa)
            st.session_state['kml_data'] = kml.kml()
            
            st.success("Processamento concluído!")

        except Exception as e:
            st.error(f"Erro: {e}")

# --- EXIBIÇÃO DO MAPA E DOWNLOAD ---
if st.session_state['df_processado'] is not None:
    df_mapa = st.session_state['df_processado']
    
    st.markdown("---")
    st.subheader("🗺️ Pré-visualização da Diretriz")
    
    # Centralizar mapa na média das coordenadas
    m = folium.Map(location=[df_mapa['lat'].mean(), df_mapa['lon'].mean()], zoom_start=15, control_scale=True)
    
    # Desenhar a linha no mapa interativo (Folium)
    pontos_linha = df_mapa[['lat', 'lon']].values.tolist()
    folium.PolyLine(pontos_linha, color="red", weight=4, opacity=0.8).add_to(m)
    
    # Adicionar marcadores (apenas alguns para não travar o mapa se forem muitos)
    for i, row in df_mapa.iterrows():
        if i % 5 == 0: # Mostra uma estaca a cada 5 para manter performance
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=3,
                popup=f"Estaca: {row['estaca']}<br>Cota: {row['z']}m",
                color="blue",
                fill=True
            ).add_to(m)

    st_folium(m, width=1100, height=500)
    
    st.download_button("📥 Baixar KML 3D (Eixo + Pontos)", st.session_state['kml_data'], "diretriz_projeto_3d.kml")
