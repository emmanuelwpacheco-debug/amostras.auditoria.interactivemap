import streamlit as st
import pandas as pd
import pdfplumber
import simplekml
from pyproj import Transformer
import io

st.set_page_config(page_title="Diretriz Estruturada (Projeto)", layout="wide")

st.title("🛣️ Traçado de Diretriz de Projeto")
st.markdown("Extração de coordenadas UTM e cotas (Z) a partir de tabelas de projeto em PDF.")

# --- SIDEBAR ---
st.sidebar.header("Configurações do Projeto")
uploaded_pdf = st.sidebar.file_uploader("Upload do PDF de Locação", type=['pdf'])
zona_utm = st.sidebar.number_input("Zona UTM (ex: 22 ou 23)", value=22, step=1)
hemisferio = st.sidebar.selectbox("Hemisfério", ["Sul", "Norte"], index=0)

# --- FUNÇÕES TÉCNICAS ---
def converter_utm_para_wgs(df, zona, hemis):
    # Configura o conversor UTM -> WGS84
    srid = f"+proj=utm +zone={zona} +{'south' if hemis == 'Sul' else 'north'} +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    transformer = Transformer.from_crs(srid, "EPSG:4326")
    
    # Aplica a conversão
    lats, lons = transformer.transform(df['Easting (X)'].values, df['Northing (Y)'].values)
    df['Latitude'] = lats
    df['Longitude'] = lons
    return df

# --- LÓGICA PRINCIPAL ---
if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        st.info(f"O PDF possui {len(pdf.pages)} páginas.")
        
        # Aqui o usuário deve indicar qual página contém a tabela para evitar processamento inútil
        pag_alvo = st.number_input("Página da Tabela de Coordenadas", min_value=1, max_value=len(pdf.pages), value=1)
        
        table = pdf.pages[pag_alvo-1].extract_table()
        
        if table:
            df_projeto = pd.DataFrame(table[1:], columns=table[0]) # Assume que a primeira linha é o cabeçalho
            st.write("### Prévia dos Dados Extraídos")
            st.dataframe(df_projeto.head())
            
            # MAPEAMENTO DE COLUNAS (O usuário seleciona quais colunas são o quê)
            cols = df_projeto.columns.tolist()
            col_x = st.selectbox("Coluna do X (Easting)", cols)
            col_y = st.selectbox("Coluna do Y (Northing)", cols)
            col_z = st.selectbox("Coluna da Cota (Z)", cols)
            col_estaca = st.selectbox("Coluna da Estaca/Nome", cols)

            if st.button("Gerar KML Estruturado"):
                try:
                    # Limpeza de dados (remover caracteres não numéricos)
                    df_projeto[col_x] = pd.to_numeric(df_projeto[col_x].astype(str).str.replace(',', '.'), errors='coerce')
                    df_projeto[col_y] = pd.to_numeric(df_projeto[col_y].astype(str).str.replace(',', '.'), errors='coerce')
                    df_projeto[col_z] = pd.to_numeric(df_projeto[col_z].astype(str).str.replace(',', '.'), errors='coerce')
                    df_projeto = df_projeto.dropna(subset=[col_x, col_y])

                    # Renomeia para facilitar a função de conversão
                    df_projeto = df_projeto.rename(columns={col_x: 'Easting (X)', col_y: 'Northing (Y)'})
                    
                    # Converte coordenadas
                    df_final = converter_utm_para_wgs(df_projeto, zona_utm, hemisferio)
                    
                    # Criação do KML 3D
                    kml = simplekml.Kml()
                    ls = kml.newlinestring(name="Eixo do Projeto")
                    
                    coords_3d = []
                    for _, row in df_final.iterrows():
                        # Tupla (Longitude, Latitude, Altitude)
                        coords_3d.append((row['Longitude'], row['Latitude'], row[col_z]))
                        
                        # Adiciona um ponto (placemark) para cada estaca
                        pnt = kml.newpoint(name=str(row[col_estaca]))
                        pnt.coords = [(row['Longitude'], row['Latitude'], row[col_z])]
                        pnt.altitudemode = simplekml.AltitudeMode.absolute # Faz o ponto "flutuar" na cota real

                    ls.coords = coords_3d
                    ls.altitudemode = simplekml.AltitudeMode.absolute
                    ls.style.linestyle.width = 3
                    ls.style.linestyle.color = simplekml.Color.red

                    # Download
                    kml_str = kml.kml()
                    st.download_button("📥 Baixar KML da Diretriz 3D", kml_str, "diretriz_projeto.kml")
                    
                except Exception as e:
                    st.error(f"Erro no processamento: {e}")
        else:
            st.warning("Nenhuma tabela detectada na página selecionada.")
