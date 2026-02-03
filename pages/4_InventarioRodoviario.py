import streamlit as st
import pandas as pd
import geopandas as gpd
import fiona
import io
import zipfile
import os

# Configuração da página
st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

# Habilitar suporte a KML no fiona
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

st.title("🗺️ Inventário e Filtro de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ ou KML das Rodovias", type=['kmz', 'kml'])

def carregar_dados(file):
    # Se for KMZ, precisamos descompactar para extrair o doc.kml interno
    if file.name.lower().endswith('.kmz'):
        with zipfile.ZipFile(file, 'r') as z:
            # Procura pelo arquivo kml dentro do kmz
            kml_filename = [f for f in z.namelist() if f.endswith('.kml')][0]
            with z.open(kml_filename) as kml_file:
                content = kml_file.read()
                # fiona.BytesCollection é a forma correta de ler bytes de KML
                with fiona.BytesCollection(content) as col:
                    return gpd.GeoDataFrame.from_features(col)
    else:
        # Leitura direta para KML
        with fiona.BytesCollection(file.read()) as col:
            return gpd.GeoDataFrame.from_features(col)

if uploaded_file:
    try:
        # Carregamento usando a nova função corrigida
        df_geo = carregar_dados(uploaded_file)
        
        st.success(f"Arquivo carregado com sucesso! {len(df_geo)} trechos encontrados.")

        # --- CONFIGURAÇÃO DE COLUNAS ---
        st.subheader("⚙️ Configuração dos Dados")
        cols = df_geo.columns.tolist()
        
        # Tentativa de pré-seleção inteligente
        def buscar_indice(lista, termos):
            for i, c in enumerate(lista):
                if any(t in c.upper() for t in termos): return i
            return 0

        c1, c2, c3 = st.columns(3)
        with c1: col_revest = st.selectbox("Coluna de Revestimento", cols, index=buscar_indice(cols, ['PAV', 'REVEST', 'TIPO']))
        with c2: col_rodovia = st.selectbox("Coluna da Rodovia", cols, index=buscar_indice(cols, ['ROD', 'NOME', 'SIGLA']))
        with c3: col_extensao = st.selectbox("Coluna de Extensão (km)", cols, index=buscar_indice(cols, ['EXT', 'KM', 'COMP']))

        # --- FILTROS ---
        tipos_pav = sorted(df_geo[col_revest].unique().astype(str).tolist())
        selecionados = st.multiselect("Filtrar por Revestimento:", tipos_pav, default=tipos_pav)

        # Processamento do Filtro
        df_filtrado = df_geo[df_geo[col_revest].isin(selecionados)].copy()

        # Conversão de extensão para número (limpeza de strings)
        df_filtrado[col_extensao] = pd.to_numeric(
            df_filtrado[col_extensao].astype(str).str.replace('.', '').str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0)

        # --- PAINEL DE RESULTADOS ---
        ext_total = df_filtrado[col_extensao].sum()
        
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("Trechos Selecionados", len(df_filtrado))
        m2.metric("Extensão Total", f"{ext_total:.2f} km")

        # Exibição da tabela (sem a coluna de geometria que é pesada)
        st.dataframe(df_filtrado.drop(columns=['geometry']), use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar Relatório")
        
        # Gerar Excel em memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_filtrado.drop(columns=['geometry']).to_excel(writer, index=False, sheet_name='Inventario')
        
        st.download_button(
            label="Baixar Relatório em Excel",
            data=output.getvalue(),
            file_name="inventario_filtrado_GO.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        st.info("Dica: Verifique se o arquivo KMZ contém camadas de vetores válidas.")
