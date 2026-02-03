import streamlit as st
import pandas as pd
import geopandas as gpd
import fiona
import io
import simplekml

st.set_page_config(page_title="Inventário Rodoviário", layout="wide")

st.title("🛣️ Inventário e Filtro de Revestimento")

# Habilitar suporte a KML/KMZ no fiona
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

# --- SIDEBAR ---
uploaded_kmz = st.sidebar.file_uploader("Carregar KMZ das Rodovias (GO)", type=['kmz', 'kml'])

if uploaded_kmz:
    try:
        # Leitura do arquivo usando Geopandas
        # KMZ é um ZIP, então o Geopandas precisa ler de forma específica
        with fiona.BytesCollection(uploaded_kmz.read()) as f:
            df_geo = gpd.from_features(f)
        
        st.success(f"KMZ carregado com {len(df_geo)} trechos identificados.")
        
        # --- FILTROS ---
        st.subheader("🔍 Filtros de Pesquisa")
        
        # Identificar automaticamente as colunas de Revestimento e Nome da Rodovia
        # (Ajuste os nomes das colunas conforme aparecem no seu arquivo)
        colunas = df_geo.columns.tolist()
        
        c1, c2 = st.columns(2)
        with c1:
            col_revest = st.selectbox("Selecione a coluna de Revestimento:", colunas)
        with c2:
            col_nome = st.selectbox("Selecione a coluna Nome/Sigla:", colunas)
            
        # Criar os filtros baseados nos dados reais
        tipos_revestimento = df_geo[col_revest].unique().tolist()
        revest_selecionado = st.multiselect("Filtrar por Tipo de Pavimento:", tipos_revestimento, default=tipos_revestimento)
        
        # Aplicação do Filtro
        df_filtrado = df_geo[df_geo[col_revest].isin(revest_selecionado)]
        
        st.write(f"Exibindo **{len(df_filtrado)}** trechos após filtros.")
        st.dataframe(df_filtrado.drop(columns=['geometry'])) # Mostra tabela sem a coluna geométrica pesada

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar Resultados")
        ce1, ce2 = st.columns(2)
        
        with ce1:
            # Exportar Excel
            output_excel = io.BytesIO()
            df_filtrado.drop(columns=['geometry']).to_excel(output_excel, index=False)
            st.download_button("Excel (.xlsx)", output_excel.getvalue(), "relatorio_rodovias.xlsx")
            
        with ce2:
            # Exportar KML (simplificado para visualização rápida)
            # Como converter Geodataframe para KML pode ser complexo, 
            # podemos baixar o shapefile ou GeoJSON se preferir.
            if st.button("Gerar KML dos Filtros"):
                # Lógica simples para gerar KML a partir das linhas
                kml = simplekml.Kml()
                for _, row in df_filtrado.iterrows():
                    # Adiciona a geometria no KML (Linestring ou Multilinestring)
                    # Esta parte requer tratamento da geometria dependendo do tipo
                    st.info("Função de exportação KML em processamento...")

    except Exception as e:
        st.error(f"Erro ao ler o KMZ: {e}. Certifique-se de que o arquivo é um KMZ válido.")
