import streamlit as st
import pandas as pd
import zipfile
import xml.etree.ElementTree as ET
import io
import re
from bs4 import BeautifulSoup
import simplekml

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

st.title("🗺️ Inventário e Exportador de KMZ (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias (GOINFRA)", type=['kmz'])

def extrair_tabela_goinfra(html_str):
    """Extrai dados especificamente do formato de tabela da GOINFRA"""
    dados = {}
    if not html_str or not isinstance(html_str, str):
        return dados
    soup = BeautifulSoup(html_str, 'html.parser')
    linhas = soup.find_all('tr')
    for linha in linhas:
        colunas = linha.find_all('td')
        if len(colunas) >= 2:
            chave = colunas[0].get_text(strip=True).upper().replace(':', '')
            valor = colunas[1].get_text(strip=True)
            if chave:
                dados[chave] = valor
    return dados

def parse_kmz_completo(file):
    """Extrai dados e preserva a geometria para re-gerar o KMZ"""
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
            # 1. Extrai Atributos da Descrição HTML
            desc = pm.find('kml:description', ns)
            if desc is not None and desc.text:
                row.update(extrair_tabela_goinfra(desc.text))
            
            # 2. Extrai Coordenadas (para poder gerar o KMZ depois)
            coords_tag = pm.find('.//kml:coordinates', ns)
            if coords_tag is not None:
                row['GEOMETRIA_RAW'] = coords_tag.text.strip()
            
            # 3. Identificador
            name = pm.find('kml:name', ns)
            row['NOME_TRECHO'] = name.text if name is not None else "Sem Nome"
            
            if row: registros.append(row)
            
        return pd.DataFrame(registros)
    except Exception as e:
        return f"Erro: {e}"

def limpar_extensao_v3(val):
    """Limpeza ultra-robusta de valores de KM"""
    if pd.isna(val): return 0.0
    s = str(val).lower().replace('km', '').strip()
    # Se houver ponto e vírgula, o ponto é milhar (ex: 1.250,50)
    if '.' in s and ',' in s:
        s = s.replace('.', '')
    s = s.replace(',', '.') # Padroniza para decimal americano
    try:
        return float(re.sub(r'[^\d.]', '', s))
    except:
        return 0.0

if uploaded_file:
    with st.spinner("Processando inventário e geometrias..."):
        df_dados = parse_kmz_completo(uploaded_file)
    
    if isinstance(df_dados, str):
        st.error(df_dados)
    else:
        cols = [c for c in df_dados.columns if c != 'GEOMETRIA_RAW']
        
        # Identificação Inteligente
        def achar_col(termos):
            for i, c in enumerate(cols):
                if any(t in c.upper() for t in termos): return i
            return 0

        st.subheader("📊 Filtros de Auditoria")
        c1, c2, c3 = st.columns(3)
        with c1: col_rev = st.selectbox("Coluna Revestimento", cols, index=achar_col(['REVEST', 'PAV']))
        with c2: col_rod = st.selectbox("Coluna Rodovia", cols, index=achar_col(['ROD', 'SIGLA', 'GO-']))
        with c3: col_ext = st.selectbox("Coluna Extensão", cols, index=achar_col(['EXTENS', 'KM']))

        # Filtro Dinâmico
        opcoes = sorted(df_dados[col_rev].unique().astype(str).tolist())
        selecionados = st.multiselect("Tipos de Pavimento:", opcoes, default=opcoes)
        
        df_f = df_dados[df_dados[col_rev].isin(selecionados)].copy()
        
        # Quantificação Corrigida
        df_f['KM_NUM'] = df_f[col_ext].apply(limpar_extensao_v3)
        total_km = df_f['KM_NUM'].sum()

        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Trechos", len(df_f))
        m2.metric("Extensão Total", f"{total_km:.2f} km")
        m3.metric("Rodovias", df_f[col_rod].nunique())

        st.dataframe(df_f.drop(columns=['GEOMETRIA_RAW', 'KM_NUM'], errors='ignore'), use_container_width=True)

        # --- EXPORTAÇÃO ---
        st.subheader("📥 Exportar Resultados Selecionados")
        ce1, ce2 = st.columns(2)

        with ce1:
            # EXCEL
            buffer_ex = io.BytesIO()
            df_f.drop(columns=['GEOMETRIA_RAW', 'KM_NUM']).to_excel(buffer_ex, index=False)
            st.download_button("📊 Baixar Planilha Excel", buffer_ex.getvalue(), "inventario_filtrado.xlsx")

        with ce2:
            # KMZ (Re-gerado a partir dos filtrados)
            if st.button("🗺️ Gerar Novo KMZ dos Filtrados"):
                try:
                    kml_new = simplekml.Kml()
                    for _, row in df_f.iterrows():
                        if pd.notna(row.get('GEOMETRIA_RAW')):
                            # Criar o placemark
                            pnt = kml_new.newlinestring(name=str(row[col_rod]))
                            # Converter string de coordenadas KML para lista de tuplas
                            coords_list = []
                            for c in row['GEOMETRIA_RAW'].split():
                                part = c.split(',')
                                if len(part) >= 2:
                                    coords_list.append((float(part[0]), float(part[1])))
                            pnt.coords = coords_list
                            pnt.description = f"Revestimento: {row[col_rev]}\nExtensão: {row[col_ext]}"
                    
                    # Salva como KMZ (zipado)
                    kmz_buffer = io.BytesIO()
                    with zipfile.ZipFile(kmz_buffer, 'w') as zf:
                        zf.writestr("doc.kml", kml_new.kml())
                    
                    st.download_button("📥 Baixar KMZ Filtrado", kmz_buffer.getvalue(), "rodovias_selecionadas.kmz")
                    st.success("KMZ Gerado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao gerar KMZ: {e}")
