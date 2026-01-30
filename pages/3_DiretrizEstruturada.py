import streamlit as st
import pandas as pd
import pdfplumber
import simplekml
from pyproj import Transformer
import io

st.set_page_config(page_title="Diretriz Estruturada", layout="wide")

# --- INICIALIZAÇÃO DO ESTADO ---
if 'df_projeto' not in st.session_state:
    st.session_state['df_projeto'] = None

st.title("🛣️ Diretriz Estruturada (Nota de Serviço)")

# --- SIDEBAR ---
st.sidebar.header("Configurações")
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
                    # Criamos o DF sem cabeçalho para evitar o erro de nomes duplicados
                    temp_df = pd.DataFrame(table)
                    dados_acumulados.append(temp_df)
            
            if dados_acumulados:
                # Salva no session_state para não sumir ao clicar nos selectboxes
                st.session_state['df_projeto'] = pd.concat(dados_acumulados, ignore_index=True)
                st.rerun()

# --- INTERFACE DE MAPEAMENTO ---
if st.session_state['df_projeto'] is not None:
    df_raw = st.session_state['df_projeto']
    
    st.subheader("📍 Identificação de Colunas")
    st.info("Selecione os índices das colunas baseando-se na prévia abaixo:")
    
    cols_idx = list(range(len(df_raw.columns)))
    
    c1, c2, c3, c4, c5 = st.columns(5)
    # Sugestão de índices baseada na imagem da Nota de Serviço
    with c1: idx_estaca = st.selectbox("Índice Estaca (+)", cols_idx, index=9)
    with c2: idx_norte = st.selectbox("Índice Norte (Y)", cols_idx, index=11)
    with c3: idx_leste = st.selectbox("Índice Leste (X)", cols_idx, index=12)
    with c4: idx_cter = st.selectbox("Índice Cota Terreno", cols_idx, index=13)
    with c5: idx_cproj = st.selectbox("Índice Cota Projeto", cols_idx, index=14)

    # Exibe a prévia para o usuário conferir
    st.dataframe(df_raw.head(20))

    if st.button("🛰️ Gerar KML e Processar Dados"):
        try:
            # Filtragem: Mantém apenas linhas onde a coluna de coordenadas tem números
            df_limpo = df_raw[df_raw[idx_norte].str.contains(r'\d', na=False)].copy()
            
            def limpar_num(val):
                if not val: return 0.0
                return float(str(val).replace('.', '').replace(',', '.'))

            # Conversão UTM -> WGS84
            srid = f"+proj=utm +zone={zona_utm} +{'south' if hemisferio == 'Sul' else 'north'} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
            transformer = Transformer.from_crs(srid, "EPSG:4326")
            
            kml = simplekml.Kml()
            coords_linha = []

            for _, row in df_limpo.iterrows():
                n = limpar_num(row[idx_norte])
                l = limpar_num(row[idx_leste])
                z = limpar_num(row[idx_cproj])
                estaca = str(row[idx_estaca-1]) + " + " + str(row[idx_estaca]) # Junta Estaca e Metros
                
                lat, lon = transformer.transform(l, n)
                coords_linha.append((lon, lat, z))
                
                # Criar Ponto no KML
                pnt = kml.newpoint(name=f"Estaca {estaca}")
                pnt.coords = [(lon, lat, z)]
                pnt.altitudemode = simplekml.AltitudeMode.absolute
                pnt.description = f"Cota Terreno: {row[idx_cter]}\nCota Projeto: {row[idx_cproj]}"

            # Criar Linha do Eixo
            lin = kml.newlinestring(name="Eixo da Rodovia")
            lin.coords = coords_linha
            lin.altitudemode = simplekml.AltitudeMode.absolute
            lin.style.linestyle.color = simplekml.Color.red
            lin.style.linestyle.width = 4

            st.success(f"Processadas {len(df_limpo)} estacas com sucesso!")
            st.download_button("📥 Baixar KML 3D", kml.kml(), "diretriz_projeto_3d.kml")
            
        except Exception as e:
            st.error(f"Erro ao processar: {e}. Verifique se as colunas selecionadas contêm os números das coordenadas.")
        
