import streamlit as st
import pandas as pd
import zipfile
import xml.etree.ElementTree as ET
import io
from bs4 import BeautifulSoup # Biblioteca para limpar o HTML

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

st.title("🗺️ Inventário de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias", type=['kmz'])

def extrair_tabela_html(html_str):
    """Converte a string da coluna Description em um dicionário de dados"""
    try:
        soup = BeautifulSoup(html_str, 'html.parser')
        dados = {}
        # Busca todas as linhas da tabela dentro da descrição
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) == 2:
                chave = tds[0].get_text(strip=True)
                valor = tds[1].get_text(strip=True)
                dados[chave] = valor
        return dados
    except:
        return {}

def parse_kmz_to_df(file):
    try:
        with zipfile.ZipFile(file, 'r') as z:
            kml_name = [n for n in z.namelist() if n.endswith('.kml')][0]
            with z.open(kml_name) as f:
                tree = ET.parse(f)
                root = tree.getroot()
        
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        registros = []
        for pm in root.findall('.//kml:Placemark', ns):
            # 1. Tenta pegar dados do ExtendedData (SimpleData)
            row = {}
            for data_tag in pm.findall('.//kml:SimpleData', ns):
                row[data_tag.get('name')] = data_tag.text
            
            # 2. Se a descrição contiver HTML (seu caso), extraímos ela
            desc = pm.find('kml:description', ns)
            if desc is not None and desc.text:
                dados_html = extrair_tabela_html(desc.text)
                row.update(dados_html) # Junta os dados do HTML com a linha
            
            # 3. Adiciona o nome do Placemark como referência
            name = pm.find('kml:name', ns)
            if name is not None: row['Identificador'] = name.text
            
            if row: registros.append(row)
            
        return pd.DataFrame(registros)
    except Exception as e:
        return f"Erro: {e}"

if uploaded_file:
    with st.spinner("Processando dados e limpando tabelas HTML..."):
        df_raw = parse_kmz_to_df(uploaded_file)
    
    if isinstance(df_raw, str):
        st.error(df_raw)
    else:
        # Remove colunas totalmente vazias ou com o código HTML bruto para limpar a tela
        df_dados = df_raw.copy()
        
        st.success(f"Sucesso! {len(df_dados)} trechos processados e limpos.")

        cols = df_dados.columns.tolist()
        
        # Interface de filtros
        c1, c2, c3 = st.columns(3)
        with c1: col_rev = st.selectbox("Selecione a coluna de PAVIMENTO", cols)
        with c2: col_rod = st.selectbox("Selecione a coluna da RODOVIA", cols)
        with c3: col_ext = st.selectbox("Selecione a coluna de EXTENSÃO", cols)

        tipos = sorted(df_dados[col_rev].unique().astype(str).tolist())
        sel = st.multiselect("Filtrar Revestimento:", tipos, default=tipos)
        
        df_f = df_dados[df_dados[col_rev].isin(sel)].copy()
        
        # Limpeza e cálculo de KM
        def converter_km(val):
            try:
                # Remove unidades e ajusta separadores
                s = str(val).lower().replace('km', '').strip()
                s = s.replace('.', '').replace(',', '.')
                return float(s)
            except:
                return 0.0

        df_f['km_num'] = df_f[col_ext].apply(converter_km)
        
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("Trechos", len(df_f))
        m2.metric("Total Extensão", f"{df_f['km_num'].sum():.2f} km")

        # Exibe a tabela limpa
        st.dataframe(df_f.drop(columns=['km_num'], errors='ignore'), use_container_width=True)

        # Download
        csv = df_f.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Baixar Planilha (CSV)", csv, "inventario_limpo.csv", "text/csv")
