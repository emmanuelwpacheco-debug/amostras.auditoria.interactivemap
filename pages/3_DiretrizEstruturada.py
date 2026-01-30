import streamlit as st
import pandas as pd
import pdfplumber
import simplekml
from pyproj import Transformer
import io
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Diretriz Estruturada", layout="wide")

# --- INICIALIZAÇÃO DO ESTADO PARA MANTER OS DADOS NA MEMÓRIA ---
if 'df_projeto' not in st.session_state:
    st.session_state['df_projeto'] = None
if 'df_processado' not in st.session_state:
    st.session_state['df_processado'] = None
if 'kml_data' not in st.session_state:
    st.session_state['kml_data'] = None

st.title("🛣️ Diretriz Estruturada (Nota de Serviço)")

# --- BARRA LATERAL (SIDEBAR) ---
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
                st.session_state['df_processado'] = None # Limpa processamento anterior
                st.rerun()

# --- INTERFACE DE MAPEAMENTO ---
if st.session_state['df_projeto'] is not None:
    df_raw = st.session_state['df_projeto']
    
    st.subheader("📍 Mapeamento de Colunas")
    st.info("Identifique os índices das colunas centrais (Eixo) na tabela abaixo.")
    
    cols_idx = list(range(len(df_raw.columns)))
    
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: idx_estaca = st.selectbox("Índice Estaca (+)", cols_idx, index=9)
    with c2: idx_norte = st.selectbox("Norte (Y)", cols_idx, index=11)
    with c3: idx_leste = st.selectbox("Leste (X)", cols_idx, index=12)
    with c4: idx_cter = st.selectbox("Cota Terreno", cols_idx, index=13)
    with c5: idx_cproj = st.selectbox("Cota Projeto", cols_idx, index=14)

    st.dataframe(df_raw.head(15))

    if st.button("🛰️ Processar e Gerar Visualização"):
        try:
            # Filtragem: remove linhas que não possuem coordenadas (cabeçalhos repetidos)
            df_limpo = df_raw[df_raw[idx_norte].str.contains(r'\d', na=False)].copy()
            
            def limpar_num(val):
                if not val: return 0.0
                return float(str(val).replace('.', '').replace(',', '.'))

            # Configuração Projeção
            srid = f"+proj=utm +zone={zona_utm} +{'south' if hemisferio == 'Sul' else 'north'} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            transformer = Transformer.from_crs(srid, "EPSG:4326")
            
            kml = simplekml.Kml()
            coords_kml = []
            pontos_mapa = []
            total_linhas = len(df_limpo)

            for i, (_, row) in enumerate(df_limpo.iterrows()):
                n = limpar_num(row[idx_norte])
                l = limpar_num(row[idx_leste])
                z = limpar_num(row[idx_cproj])
                
                # Formata o nome da estaca de forma limpa
                e_inteira = str(row[idx_estaca-1]).split('.')[0]
                e_metro = str(row[idx_estaca]).replace(',', '.')
                label_completa = f"{e_inteira} + {e_metro}"
                
                lat, lon = transformer.transform(l, n)
                coords_kml.append((lon, lat, z))
                
                pontos_mapa.append({
                    'lat': lat, 'lon': lon, 'estaca': label_completa, 'z': z, 'terreno': row[idx_cter]
                })

                # Lógica de Limpeza do KML: Label apenas em múltiplos de 10 ou na última
                try:
                    is_multiplo_10 = int(e_inteira) % 10 == 0
                except:
                    is_multiplo_10 = False
                
                nome_kml = label_completa if (is_multiplo_10 or i == total_linhas - 1) else ""
                
                pnt = kml.newpoint(name=nome_kml)
                pnt.coords = [(lon, lat, z)]
                pnt.altitudemode = simplekml.AltitudeMode.absolute
                pnt.description = f"Estaca: {label_completa}\nCota Projeto: {z}m\nCota Terreno: {row[idx_cter]}m"
                
                if not nome_kml:
                    pnt.style.iconstyle.scale = 0.3 # Ponto pequeno para não poluir

            # Linha 3D no KML
            lin = kml.newlinestring(name="Eixo 3D")
            lin.coords = coords_kml
            lin.altitudemode = simplekml.AltitudeMode.absolute
            lin.style.linestyle.color = simplekml.Color.red
            lin.style.linestyle.width = 4
            
            st.session_state['df_processado'] = pd.DataFrame(pontos_mapa)
            st.session_state['kml_data'] = kml.kml()
            st.rerun()

        except Exception as e:
            st.error(f"Erro no processamento: {e}")

# --- MAPA E DOWNLOAD ---
if st.session_state['df_processado'] is not None:
    df_m = st.session_state['df_processado']
    total = len(df_m)
    
    st.markdown("---")
    st.subheader("🗺️ Pré-visualização da Diretriz")
    
    m = folium.Map(location=[df_m['lat'].mean(), df_m['lon'].mean()], zoom_start=16)
    
    # Traçado da linha no mapa
    folium.PolyLine(df_m[['lat', 'lon']].values.tolist(), color="red", weight=3).add_to(m)
    
    # Marcadores: Primeiro, Último e Múltiplos de 10
    for i, row in df_m.iterrows():
        try:
            est_num = int(row['estaca'].split(' + ')[0])
            is_10 = est_num % 10 == 0
        except:
            is_10 = False

        if i == 0 or i == total - 1 or is_10:
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=5,
                popup=f"Estaca: {row['estaca']}<br>Cota: {row['z']}m",
                color="blue" if i != total - 1 else "green", # Último ponto em verde
                fill=True,
                fill_opacity=0.7
            ).add_to(m)

    st_folium(m, width=1100, height=500)
    st.download_button("📥 Baixar KML Final (3D + Eixo)", st.session_state['kml_data'], "diretriz_projeto_final.kml")
