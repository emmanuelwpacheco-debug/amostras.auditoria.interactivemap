import streamlit as st
import pandas as pd
import geopandas as gpd
import fiona
import io
import zipfile

# Configuração inicial
st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

# Forçar suporte a KML no Fiona
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

st.title("🗺️ Inventário e Filtro de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ ou KML das Rodovias", type=['kmz', 'kml'])

def processar_dados_geograficos(file):
    """Lida com a abertura de KMZ/KML e converte para GeoDataFrame de forma segura"""
    if file.name.lower().endswith('.kmz'):
        with zipfile.ZipFile(file, 'r') as z:
            kml_name = [n for n in z.namelist() if n.endswith('.kml')][0]
            with z.open(kml_name) as kml_file:
                kml_bytes = kml_file.read()
    else:
        kml_bytes = file.read()

    # Em vez de gpd.from_features, usamos fiona para ler os bytes e converter para GDF
    with fiona.BytesCollection(kml_bytes) as collection:
        # Criamos o GeoDataFrame a partir da lista de features da coleção
        gdf = gpd.GeoDataFrame.from_features([feature for feature in collection])
        # Define o sistema de coordenadas se não houver (KML é sempre WGS84)
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        return gdf

if uploaded_file:
    try:
        # Carregamento Robusto
        with st.spinner("Lendo e convertendo dados geográficos..."):
            df_geo = processar_dados_geograficos(uploaded_file)
        
        st.success(f"Arquivo carregado! {len(df_geo)} registros identificados.")

        # --- MAPEAMENTO DE COLUNAS ---
        st.subheader("⚙️ Configuração dos Dados")
        cols = df_geo.columns.tolist()
        
        c1, c2, c3 = st.columns(3)
        with c1: col_revest = st.selectbox("Coluna de Revestimento", cols, index=0)
        with c2: col_rodovia = st.selectbox("Coluna da Rodovia", cols, index=0)
        with c3: col_extensao = st.selectbox("Coluna de Extensão", cols, index=0)

        # --- FILTRAGEM ---
        tipos_pav = sorted(df_geo[col_revest].unique().astype(str).tolist())
        selecionados = st.multiselect("Selecione os Pavimentos:", tipos_pav, default=tipos_pav)

        df_filtrado = df_geo[df_geo[col_revest].isin(selecionados)].copy()

        # Limpeza Numérica (Lida com '1.234,56', '10 km', etc)
        def limpar_km(valor):
            if pd.isna(valor): return 0.0
            s = str(valor).replace('km', '').replace('KM', '').strip()
            s = s.replace('.', '').replace(',', '.')
            try: return float(s)
            except: return 0.0

        df_filtrado['ext_num'] = df_filtrado[col_extensao].apply(limpar_km)
        ext_total = df_filtrado['ext_num'].sum()

        # --- EXIBIÇÃO ---
        st.divider()
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Trechos", len(df_filtrado))
        col_m2.metric("Total Extensão", f"{ext_total:.2f} km")

        # Remover geometria para exibir a tabela (mais rápido e evita erros de renderização)
        df_display = df_filtrado.drop(columns=['geometry', 'ext_num'], errors='ignore')
        st.dataframe(df_display, use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_display.to_excel(writer, index=False)
        
        st.download_button(
            label="Baixar Relatório Excel",
            data=buffer.getvalue(),
            file_name="inventario_go.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Erro crítico: {e}")
        st.warning("Verifique se o seu KMZ não está vazio ou corrompido.")
