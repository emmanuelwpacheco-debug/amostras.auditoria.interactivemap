import streamlit as st
import pandas as pd
import geopandas as gpd
import fiona
import zipfile
import io

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

# Habilitar drivers KML
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

st.title("🗺️ Inventário de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias", type=['kmz'])

@st.cache_data # Cache para não travar o app ao reprocessar
def ler_kmz_otimizado(file):
    try:
        # Extrair KML de dentro do KMZ em memória
        with zipfile.ZipFile(file, 'r') as z:
            kml_name = [n for n in z.namelist() if n.endswith('.kml')][0]
            with z.open(kml_name) as kml_file:
                content = kml_file.read()
        
        # Leitura via Fiona (mais leve que geopandas direto)
        with fiona.BytesCollection(content) as col:
            # Extraímos apenas as propriedades (atributos), ignorando a geometria pesada no início
            data = [feature['properties'] for feature in col]
            df = pd.DataFrame(data)
            return df
    except Exception as e:
        return str(e)

if uploaded_file:
    with st.spinner("Processando inventário... (Arquivos grandes podem levar 1 minuto)"):
        df_dados = ler_kmz_otimizado(uploaded_file)
    
    if isinstance(df_dados, str):
        st.error(f"Erro na leitura: {df_dados}")
    else:
        st.success(f"Sucesso! {len(df_dados)} trechos carregados.")

        # --- FILTROS ---
        cols = df_dados.columns.tolist()
        
        c1, c2, c3 = st.columns(3)
        with c1: col_revest = st.selectbox("Coluna Revestimento", cols, index=0)
        with c2: col_rod = st.selectbox("Coluna Rodovia", cols, index=0)
        with c3: col_ext = st.selectbox("Coluna Extensão", cols, index=0)

        # Filtro de Pavimento
        tipos = sorted(df_dados[col_revest].unique().astype(str).tolist())
        selecionados = st.multiselect("Selecione os tipos:", tipos, default=tipos)
        
        df_filtrado = df_dados[df_dados[col_revest].isin(selecionados)].copy()

        # Limpeza Numérica
        def clean_num(x):
            try:
                return float(str(x).replace('.', '').replace(',', '.'))
            except:
                return 0.0

        df_filtrado['ext_calculada'] = df_filtrado[col_ext].apply(clean_num)
        
        # --- EXIBIÇÃO ---
        m1, m2 = st.columns(2)
        m1.metric("Trechos Selecionados", len(df_filtrado))
        m2.metric("Extensão Total", f"{df_filtrado['ext_calculada'].sum():.2f} km")

        st.dataframe(df_filtrado, use_container_width=True)

        # Exportação
        output = io.BytesIO()
        df_filtrado.to_excel(output, index=False)
        st.download_button("📥 Baixar Excel", output.getvalue(), "inventario_goias.xlsx")
