import streamlit as st
import pandas as pd
import pdfplumber
import simplekml
from pyproj import Transformer
import io

st.set_page_config(page_title="Diretriz Estruturada", layout="wide")

st.title("🛣️ Diretriz Estruturada (Nota de Serviço)")

# --- SIDEBAR ---
st.sidebar.header("Configurações")
uploaded_pdf = st.sidebar.file_uploader("Upload da Nota de Serviço (PDF)", type=['pdf'])
zona_utm = st.sidebar.number_input("Zona UTM", value=23)
hemisferio = st.sidebar.selectbox("Hemisfério", ["Sul", "Norte"])

# --- FUNÇÃO DE CONVERSÃO ---
def converter_utm_para_wgs(df, zona, hemis, col_n, col_l):
    srid = f"+proj=utm +zone={zona} +{'south' if hemis == 'Sul' else 'north'} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    transformer = Transformer.from_crs(srid, "EPSG:4326")
    
    # Limpeza de strings (remove pontos de milhar e troca vírgula por ponto)
    def limpar_num(val):
        if not val: return 0.0
        return float(str(val).replace('.', '').replace(',', '.'))

    df['N_clean'] = df[col_n].apply(limpar_num)
    df['L_clean'] = df[col_l].apply(limpar_num)
    
    lats, lons = transformer.transform(df['L_clean'].values, df['N_clean'].values)
    df['Latitude'] = lats
    df['Longitude'] = lons
    return df

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        total_pags = len(pdf.pages)
        st.sidebar.info(f"Total de páginas: {total_pags}")
        
        # Seleção de intervalo de páginas
        p_ini, p_fim = st.sidebar.slider("Intervalo de páginas para extração", 1, total_pags, (1, total_pags))
        
        dados_acumulados = []
        
        if st.button("🔍 Extrair Dados das Páginas Selecionadas"):
            for i in range(p_ini - 1, p_fim):
                page = pdf.pages[i]
                table = page.extract_table()
                if table:
                    # Transformamos em DataFrame
                    temp_df = pd.DataFrame(table)
                    
                    # Como a tabela tem cabeçalhos complexos, vamos renomear colunas pela posição
                    # Olhando sua imagem: Estaca (col 4 e 5), Norte (col 6), Leste (col 7), Cota Terreno (col 8), Cota Projeto (col 9)
                    # Nota: As posições podem variar levemente se houver colunas vazias detectadas
                    dados_acumulados.append(temp_df)
            
            if dados_acumulados:
                df_raw = pd.concat(dados_acumulados, ignore_index=True)
                
                st.write("### Identificação de Colunas")
                st.warning("As tabelas de PDF podem vir com nomes genéricos (0, 1, 2...). Identifique as colunas corretas abaixo:")
                
                col_preview = st.columns(5)
                cols_lista = df_raw.columns.tolist()
                
                with col_preview[0]: c_est = st.selectbox("Estaca", cols_lista, index=min(4, len(cols_lista)-1))
                with col_preview[1]: c_nor = st.selectbox("Norte (Y)", cols_lista, index=min(6, len(cols_lista)-1))
                with col_preview[2]: c_les = st.selectbox("Leste (X)", cols_lista, index=min(7, len(cols_lista)-1))
                with col_preview[3]: c_cter = st.selectbox("Cota Terreno", cols_lista, index=min(8, len(cols_lista)-1))
                with col_preview[4]: c_cproj = st.selectbox("Cota Projeto", cols_lista, index=min(9, len(cols_lista)-1))

                # Filtragem de linhas inválidas (cabeçalhos repetidos e linhas vazias)
                df_limpo = df_raw[df_raw[c_nor].str.contains(r'\d', na=False)].copy()
                
                st.dataframe(df_limpo.head(15))

                if st.button("🛰️ Gerar KML 3D"):
                    try:
                        df_final = converter_utm_para_wgs(df_limpo, zona_utm, hemisferio, c_nor, c_les)
                        
                        kml = simplekml.Kml()
                        # Estilo para as estacas
                        for _, row in df_final.iterrows():
                            # Limpeza da Cota Projeto para o KML
                            z = float(str(row[c_cproj]).replace(',', '.'))
                            
                            pnt = kml.newpoint(name=f"Estaca {row[c_est]}")
                            pnt.coords = [(row['Longitude'], row['Latitude'], z)]
                            pnt.altitudemode = simplekml.AltitudeMode.absolute
                            pnt.description = f"Cota Terreno: {row[c_cter]}\nCota Projeto: {row[c_cproj]}"

                        # Linha do Eixo
                        lin = kml.newlinestring(name="Eixo Projetado")
                        lin.coords = [(r['Longitude'], r['Latitude'], float(str(r[c_cproj]).replace(',', '.'))) for _, r in df_final.iterrows()]
                        lin.altitudemode = simplekml.AltitudeMode.absolute
                        lin.style.linestyle.color = simplekml.Color.cyan
                        lin.style.linestyle.width = 4

                        buf = io.BytesIO()
                        kml_str = kml.kml()
                        st.download_button("📥 Baixar Diretriz KML", kml_str, "diretriz_projeto.kml")
                    except Exception as e:
                        st.error(f"Erro ao processar valores: {e}")
