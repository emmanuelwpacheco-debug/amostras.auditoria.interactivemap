import streamlit as st
import pandas as pd
import zipfile
import xml.etree.ElementTree as ET
import io
import re
from bs4 import BeautifulSoup
import simplekml

st.set_page_config(page_title="Inventário de Pavimento", layout="wide")

# --- INICIALIZAÇÃO DO ESTADO ---
if 'kmz_filtrado' not in st.session_state:
    st.session_state['kmz_filtrado'] = None

st.title("🗺️ Inventário e Exportador de KMZ (GO)")

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias", type=['kmz'])

def extrair_tabela_goinfra(html_str):
    dados = {}
    if not html_str: return dados
    soup = BeautifulSoup(html_str, 'html.parser')
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 2:
            chave = tds[0].get_text(strip=True).upper().replace(':', '')
            valor = tds[1].get_text(strip=True)
            dados[chave] = valor
    return dados

def parse_kmz_completo(file):
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
            desc = pm.find('kml:description', ns)
            if desc is not None and desc.text:
                row.update(extrair_tabela_goinfra(desc.text))
            
            coords_tag = pm.find('.//kml:coordinates', ns)
            if coords_tag is not None:
                row['GEOMETRIA_RAW'] = coords_tag.text.strip()
            
            name = pm.find('kml:name', ns)
            row['NOME_TRECHO'] = name.text if name is not None else "Sem Nome"
            if row: registros.append(row)
        return pd.DataFrame(registros)
    except Exception as e:
        return f"Erro: {e}"

def limpar_extensao(val):
    if pd.isna(val): return 0.0
    s = str(val).lower().replace('km', '').strip()
    if '.' in s and ',' in s: s = s.replace('.', '')
    s = s.replace(',', '.')
    try: return float(re.sub(r'[^\d.]', '', s))
    except: return 0.0

if uploaded_file:
    df_dados = parse_kmz_completo(uploaded_file)
    
    if isinstance(df_dados, str):
        st.error(df_dados)
    else:
        cols = [c for c in df_dados.columns if c != 'GEOMETRIA_RAW']
        
        st.subheader("📊 Filtros e Quantificação")
        c1, c2, c3 = st.columns(3)
        with c1: col_rev = st.selectbox("Pavimento", cols, index=0)
        with c2: col_rod = st.selectbox("Rodovia", cols, index=0)
        with c3: col_ext = st.selectbox("Extensão", cols, index=0)

        opcoes = sorted(df_dados[col_rev].unique().astype(str).tolist())
        sel = st.multiselect("Filtrar Revestimento:", opcoes, default=opcoes)
        
        df_f = df_dados[df_dados[col_rev].isin(sel)].copy()
        df_f['KM_NUM'] = df_f[col_ext].apply(limpar_extensao)

        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("Trechos Selecionados", len(df_f))
        m2.metric("Extensão Total", f"{df_f['KM_NUM'].sum():.2f} km")

        st.dataframe(df_f.drop(columns=['GEOMETRIA_RAW', 'KM_NUM'], errors='ignore'), use_container_width=True)

        # --- SEÇÃO DE EXPORTAÇÃO ---
        st.subheader("📥 Exportar Resultados")
        exp1, exp2 = st.columns(2)

        with exp1:
            buffer_ex = io.BytesIO()
            df_f.drop(columns=['GEOMETRIA_RAW', 'KM_NUM']).to_excel(buffer_ex, index=False)
            st.download_button("📊 Baixar Excel (.xlsx)", buffer_ex.getvalue(), "inventario_go.xlsx", key="dl_excel")

        with exp2:
            # Botão para PROCESSAR o KMZ
            if st.button("🗺️ Processar KMZ Filtrado"):
                with st.spinner("Gerando arquivo geográfico..."):
                    try:
                        kml_gen = simplekml.Kml()
                        for _, row in df_f.iterrows():
                            if pd.notna(row.get('GEOMETRIA_RAW')):
                                lin = kml_gen.newlinestring(name=str(row[col_rod]))
                                coords = []
                                for c in row['GEOMETRIA_RAW'].split():
                                    p = c.split(',')
                                    if len(p) >= 2: coords.append((float(p[0]), float(p[1])))
                                lin.coords = coords
                                lin.description = f"Pavimento: {row[col_rev]}\nExtensão: {row[col_ext]}"
                        
                        kmz_out = io.BytesIO()
                        with zipfile.ZipFile(kmz_out, 'w') as zf:
                            zf.writestr("doc.kml", kml_gen.kml())
                        
                        st.session_state['kmz_filtrado'] = kmz_out.getvalue()
                    except Exception as e:
                        st.error(f"Erro na geração: {e}")

            # Botão de DOWNLOAD (só aparece se o KMZ já foi processado no estado da sessão)
            if st.session_state['kmz_filtrado'] is not None:
                st.download_button(
                    label="📥 Clique aqui para Baixar o KMZ",
                    data=st.session_state['kmz_filtrado'],
                    file_name="rodovias_filtradas.kmz",
                    mime="application/vnd.google-earth.kmz",
                    key="dl_kmz"
                )
