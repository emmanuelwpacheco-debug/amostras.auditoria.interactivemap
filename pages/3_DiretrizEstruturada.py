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

    # ... (parte inicial do processamento igual)
            
            kml = simplekml.Kml()
            coords_para_kml = []
            lista_pontos_mapa = []
            total_pontos = len(df_limpo)

            for i, (_, row) in enumerate(df_limpo.iterrows()):
                n = limpar_num(row[idx_norte])
                l = limpar_num(row[idx_leste])
                z = limpar_num(row[idx_cproj])
                
                # Tratamento da Estaca para exibição
                parte_inteira = str(row[idx_estaca-1]).split('.')[0] # Remove decimais se houver
                parte_metro = str(row[idx_estaca]).replace(',', '.')
                estaca_label = f"{parte_inteira} + {parte_metro}"
                
                lat, lon = transformer.transform(l, n)
                coords_para_kml.append((lon, lat, z))
                
                # Dados para o Mapa Interativo
                lista_pontos_mapa.append({
                    'lat': lat, 'lon': lon, 'estaca': estaca_label, 'z': z, 'terreno': row[idx_cter]
                })
                
                # --- LÓGICA DE LIMPEZA DO KML ---
                # Só coloca Nome (Label) se for múltiplo de 10 ou se for a última estaca
                try:
                    e_multiplo_10 = int(parte_inteira) % 10 == 0
                except:
                    e_multiplo_10 = False

                nome_ponto = estaca_label if (e_multiplo_10 or i == total_pontos - 1) else ""
                
                pnt = kml.newpoint(name=nome_ponto)
                pnt.coords = [(lon, lat, z)]
                pnt.altitudemode = simplekml.AltitudeMode.absolute
                pnt.description = f"Estaca: {estaca_label}\nCota Projeto: {z}m\nCota Terreno: {row[idx_cter]}m"
                
                # Se não tiver nome, diminui o ícone para não poluir
                if not nome_ponto:
                    pnt.style.iconstyle.scale = 0.5 

            # Linha 3D
            lin = kml.newlinestring(name="Eixo da Rodovia (3D)")
            lin.coords = coords_para_kml
            lin.altitudemode = simplekml.AltitudeMode.absolute
            lin.style.linestyle.color = simplekml.Color.red
            lin.style.linestyle.width = 4
            
            st.session_state['df_processado'] = pd.DataFrame(lista_pontos_mapa)
            st.session_state['kml_data'] = kml.kml()
            
# --- EXIBIÇÃO DO MAPA ATUALIZADA ---
if st.session_state['df_processado'] is not None:
    df_mapa = st.session_state['df_processado']
    total = len(df_mapa)
    
    st.markdown("---")
    st.subheader("🗺️ Pré-visualização da Diretriz")
    
    m = folium.Map(location=[df_mapa['lat'].mean(), df_mapa['lon'].mean()], zoom_start=15)
    
    # Desenha a linha completa
    folium.PolyLine(df_mapa[['lat', 'lon']].values.tolist(), color="red", weight=3).add_to(m)
    
    # Lógica do Mapa: Mostrar 1º, último e múltiplos de 10
    for i, row in df_mapa.iterrows():
        # Condição: Primeiro, Último ou Múltiplos de 10
        deve_mostrar = (i == 0 or i == total - 1 or i % 10 == 0)
        
        if deve_mostrar:
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=4,
                popup=f"Estaca: {row['estaca']}<br>Cota: {row['z']}m",
                color="blue" if i != total -1 else "green", # Último ponto em verde
                fill=True
            ).add_to(m)

    st_folium(m, width=1100, height=500)
    st.download_button("📥 Baixar KML Limpo", st.session_state['kml_data'], "diretriz_projeto_final.kml")
