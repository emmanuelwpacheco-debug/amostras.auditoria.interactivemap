import streamlit as st
import pandas as pd
import zipfile
import xml.etree.ElementTree as ET
import io
from bs4 import BeautifulSoup

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

st.title("🗺️ Inventário de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias (GOINFRA)", type=['kmz'])

def extrair_tabela_goinfra(html_str):
    """Extrai dados especificamente do formato de tabela da GOINFRA"""
    dados = {}
    if not html_str or not isinstance(html_str, str):
        return dados
    
    soup = BeautifulSoup(html_str, 'html.parser')
    # O formato da GOINFRA geralmente usa <td> para chaves e valores
    linhas = soup.find_all('tr')
    for linha in linhas:
        colunas = linha.find_all('td')
        if len(colunas) >= 2:
            # Pega o texto, remove espaços e caracteres esquisitos
            chave = colunas[0].get_text(strip=True).upper().replace(':', '')
            valor = colunas[1].get_text(strip=True)
            if chave:
                dados[chave] = valor
    return dados

def parse_kmz_to_df(file):
    try:
        with zipfile.ZipFile(file, 'r') as z:
            kml_name = [n for n in z.namelist() if n.endswith('.kml')][0]
            with z.open(kml_name) as f:
                tree = ET.parse(f)
                root = tree.getroot()
        
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        registros = []

        # Varre todos os Placemarks (trechos de rodovias)
        for pm in root.findall('.//kml:Placemark', ns):
            row = {}
            
            # 1. Pega a descrição que contém a tabela HTML (Crucial para GOINFRA)
            desc = pm.find('kml:description', ns)
            if desc is not None and desc.text:
                dados_tabela = extrair_tabela_goinfra(desc.text)
                row.update(dados_tabela)
            
            # 2. Pega dados extras se houver (ExtendedData)
            for sd in pm.findall('.//kml:SimpleData', ns):
                row[sd.get('name').upper()] = sd.text

            # 3. Identificador básico
            name = pm.find('kml:name', ns)
            if name is not None: row['NOME_KML'] = name.text
            
            if row: registros.append(row)
            
        return pd.DataFrame(registros)
    except Exception as e:
        return f"Erro: {e}"

if uploaded_file:
    with st.spinner("Desmembrando tabelas HTML da GOINFRA..."):
        df_dados = parse_kmz_to_df(uploaded_file)
    
    if isinstance(df_dados, str):
        st.error(df_dados)
    else:
        # --- LIMPEZA DE COLUNAS VAZIAS ---
        df_dados = df_dados.dropna(axis=1, how='all')
        cols = df_dados.columns.tolist()

        # --- IDENTIFICAÇÃO INTELIGENTE ---
        # Tenta achar 'REVESTIMENTO', 'NOME' e 'EXTENSÃO' automaticamente
        def achar_col(lista, termos):
            for i, c in enumerate(lista):
                if any(t in c.upper() for t in termos): return i
            return 0

        idx_rev = achar_col(cols, ['REVEST', 'PAVIMENT', 'TIPO'])
        idx_rod = achar_col(cols, ['ROD', 'SIGLA', 'NOME', 'GO-'])
        idx_ext = achar_col(cols, ['EXTENS', 'KM', 'COMPRIM'])

        st.success(f"Sucesso! {len(df_dados)} registros processados.")

        # --- INTERFACE DE FILTROS ---
        st.subheader("📊 Filtros e Análise")
        c1, c2, c3 = st.columns(3)
        with c1: col_rev = st.selectbox("Coluna de Revestimento", cols, index=idx_rev)
        with c2: col_rod = st.selectbox("Coluna da Rodovia", cols, index=idx_rod)
        with c3: col_ext = st.selectbox("Coluna de Extensão", cols, index=idx_ext)

        # Filtro de Pavimento (Agora com nomes limpos!)
        opcoes = sorted(df_dados[col_rev].unique().astype(str).tolist())
        sel = st.multiselect("Selecione os tipos de pavimento:", opcoes, default=opcoes)
        
        df_f = df_dados[df_dados[col_rev].isin(sel)].copy()

        # Conversão de Extensão
        def clean_km(val):
            try:
                # Remove 'km', pontos de milhar e troca vírgula por ponto
                s = str(val).lower().replace('km', '').replace('.', '').replace(',', '.').strip()
                return float(s)
            except: return 0.0

        df_f['KM_REAL'] = df_f[col_ext].apply(clean_km)

        # --- DASHBOARD ---
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Trechos Filtrados", len(df_f))
        m2.metric("Extensão Total", f"{df_f['KM_REAL'].sum():.2f} km")
        m3.metric("Rodovias Identificadas", df_f[col_rod].nunique())

        # Exibe a tabela sem a coluna 'Description' bruta para não poluir
        exibir_cols = [c for c in df_f.columns if c.upper() != 'DESCRIPTION' and c != 'KM_REAL']
        st.dataframe(df_f[exibir_cols], use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_f[exibir_cols].to_excel(writer, index=False, sheet_name='Inventario')
        
        st.download_button("Baixar Excel (.xlsx)", buffer.getvalue(), "inventario_goinfra.xlsx")
