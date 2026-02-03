import streamlit as st
import pandas as pd
import zipfile
import xml.etree.ElementTree as ET
import io
from bs4 import BeautifulSoup

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

st.title("🗺️ Inventário de Revestimento (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias", type=['kmz'])

def extrair_dados_html_v2(html_str):
    """Extrai pares de chave/valor de tabelas HTML de forma ultra-robusta"""
    dados = {}
    if not html_str or not isinstance(html_str, str):
        return dados
    
    soup = BeautifulSoup(html_str, 'lxml')
    # Procura por linhas de tabela <tr> ou listas <li>
    for row in soup.find_all(['tr', 'li']):
        cols = row.find_all(['td', 'span', 'div'])
        if len(cols) >= 2:
            chave = cols[0].get_text(strip=True).replace(':', '')
            valor = cols[1].get_text(strip=True)
            if chave and valor:
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

        for pm in root.findall('.//kml:Placemark', ns):
            row = {}
            # Nome do trecho
            name = pm.find('kml:name', ns)
            if name is not None: row['Trecho_KML'] = name.text
            
            # Dados Estruturados (SimpleData)
            for sd in pm.findall('.//kml:SimpleData', ns):
                row[sd.get('name')] = sd.text
            
            # Dados na Descrição (HTML Table)
            desc = pm.find('kml:description', ns)
            if desc is not None and desc.text:
                row.update(extrair_dados_html_v2(desc.text))
            
            if row: registros.append(row)
            
        return pd.DataFrame(registros)
    except Exception as e:
        return f"Erro: {e}"

if uploaded_file:
    with st.spinner("Limpando dados e organizando colunas..."):
        df_dados = parse_kmz_to_df(uploaded_file)
    
    if isinstance(df_dados, str):
        st.error(df_dados)
    else:
        # --- IDENTIFICAÇÃO AUTOMÁTICA ---
        cols = df_dados.columns.tolist()
        
        # Lógica para adivinhar colunas
        idx_rod = 0
        idx_pav = 0
        idx_ext = 0
        
        for i, c in enumerate(cols):
            c_upper = c.upper()
            if any(x in c_upper for x in ['ROD', 'GO-', 'NOME', 'SIGLA']): idx_rod = i
            if any(x in c_upper for x in ['PAV', 'REVEST', 'TIPO', 'MATER']): idx_pav = i
            if any(x in c_upper for x in ['EXT', 'KM', 'COMP', 'DIST']): idx_ext = i

        st.success(f"Sucesso! {len(df_dados)} registros processados.")

        # --- SELEÇÃO DE COLUNAS ---
        st.subheader("⚙️ Verifique as Colunas Identificadas")
        c1, c2, c3 = st.columns(3)
        with c1: col_rod = st.selectbox("Coluna da Rodovia", cols, index=idx_rod)
        with c2: col_rev = st.selectbox("Coluna de Pavimento", cols, index=idx_pav)
        with c3: col_ext = st.selectbox("Coluna de Extensão", cols, index=idx_ext)

        # --- FILTROS ---
        tipos_pav = sorted(df_dados[col_rev].unique().astype(str).tolist())
        selecionados = st.multiselect("Filtrar por Revestimento:", tipos_pav, default=tipos_pav)
        
        df_f = df_dados[df_dados[col_rev].isin(selecionados)].copy()

        # Conversão de KM
        def clean_km(val):
            try:
                s = str(val).lower().replace('km', '').replace('.', '').replace(',', '.').strip()
                return float(s)
            except: return 0.0

        df_f['Extensão_Num'] = df_f[col_ext].apply(clean_km)

        # --- DASHBOARD ---
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Trechos", len(df_f))
        m2.metric("Extensão Total", f"{df_f['Extensão_Num'].sum():.2f} km")
        m3.metric("Rodovias Distintas", df_f[col_rod].nunique())

        st.dataframe(df_f.drop(columns=['Extensão_Num']), use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_f.to_excel(writer, index=False, sheet_name='Inventario_GO')
        
        st.download_button(
            label="Baixar Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name="inventario_filtrado_goias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
