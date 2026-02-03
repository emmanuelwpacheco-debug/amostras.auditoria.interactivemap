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

# Inicializa o estado para os botões não sumirem
if 'dados_prontos' not in st.session_state:
    st.session_state.dados_prontos = None
if 'kmz_buffer' not in st.session_state:
    st.session_state.kmz_buffer = None

uploaded_file = st.sidebar.file_uploader("Carregar KMZ das Rodovias", type=['kmz'])

def extrair_tabela_goinfra(html_str):
    dados = {}
    if not html_str: return dados
    soup = BeautifulSoup(html_str, 'html.parser')
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 2:
            chave = tds[0].get_text(strip=True).upper()
            valor = tds[1].get_text(strip=True)
            dados[chave] = valor
    return dados

def limpar_numero_br(valor):
    """Converte '1.250,50' ou '1250.50' em float de forma segura"""
    if pd.isna(valor) or valor == '': return 0.0
    s = str(valor).strip().lower().replace('km', '')
    # Se tiver vírgula e ponto, assume ponto como milhar (Padrão BR: 1.000,00)
    if ',' in s and '.' in s:
        s = s.replace('.', '')
    s = s.replace(',', '.')
    # Remove qualquer caractere que não seja número ou ponto
    s = re.sub(r'[^\d.]', '', s)
    try:
        return float(s)
    except:
        return 0.0

@st.cache_data
def processar_kmz(file_bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as z:
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
            
            coords = pm.find('.//kml:coordinates', ns)
            if coords is not None:
                row['GEOMETRIA_RAW'] = coords.text.strip()
            
            name = pm.find('kml:name', ns)
            row['NOME_KML'] = name.text if name is not None else "S/N"
            if row: registros.append(row)
        return pd.DataFrame(registros)
    except Exception as e:
        return str(e)

if uploaded_file:
    # Lemos os bytes uma vez para o cache funcionar
    file_bytes = uploaded_file.read()
    df_dados = processar_kmz(file_bytes)
    
    if isinstance(df_dados, str):
        st.error(f"Erro no processamento: {df_dados}")
    else:
        cols = [c for c in df_dados.columns if c != 'GEOMETRIA_RAW']
        
        st.subheader("🔍 Filtros")
        c1, c2, c3 = st.columns(3)
        with c1: col_rev = st.selectbox("Coluna Revestimento", cols, index=0)
        with c2: col_rod = st.selectbox("Coluna Rodovia", cols, index=0)
        with c3: col_ext = st.selectbox("Coluna Extensão", cols, index=0)

        tipos = sorted(df_dados[col_rev].unique().astype(str).tolist())
        sel = st.multiselect("Selecionar Tipos:", tipos, default=tipos)
        
        # Filtragem e Limpeza Matemática
        df_f = df_dados[df_dados[col_rev].isin(sel)].copy()
        df_f['EXT_LIMPA'] = df_f[col_ext].apply(limpar_numero_br)
        
        total_km = df_f['EXT_LIMPA'].sum()

        # Dashboard de métricas
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Trechos", len(df_f))
        m2.metric("Extensão Total", f"{total_km:.2f} km")
        m3.metric("Rodovias", df_f[col_rod].nunique())

        st.dataframe(df_f.drop(columns=['GEOMETRIA_RAW', 'EXT_LIMPA'], errors='ignore'), use_container_width=True)

        # --- SEÇÃO DE EXPORTAÇÃO (FORA DE BLOCOS CONDICIONAIS COMPLEXOS) ---
        st.subheader("📥 Exportar")
        col_btn1, col_btn2 = st.columns(2)

        # 1. Botão Excel
        output_ex = io.BytesIO()
        df_f.drop(columns=['GEOMETRIA_RAW', 'EXT_LIMPA'], errors='ignore').to_excel(output_ex, index=False)
        col_btn1.download_button(
            "📊 Baixar Planilha Excel", 
            output_ex.getvalue(), 
            "inventario_rodoviario.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # 2. Botão KMZ
        if col_btn2.button("🗺️ Gerar Arquivo KMZ"):
            try:
                kml = simplekml.Kml()
                for _, r in df_f.iterrows():
                    if pd.notna(r.get('GEOMETRIA_RAW')):
                        ls = kml.newlinestring(name=str(r[col_rod]))
                        # Converte string de coords em lista de tuplas (lon, lat)
                        pts = []
                        for coord_str in r['GEOMETRIA_RAW'].split():
                            p = coord_str.split(',')
                            if len(p) >= 2: pts.append((float(p[0]), float(p[1])))
                        ls.coords = pts
                        ls.description = f"Pavimento: {r[col_rev]} | Extensão: {r[col_ext]}"
                
                kmz_buf = io.BytesIO()
                with zipfile.ZipFile(kmz_buf, 'w') as zf:
                    zf.writestr("doc.kml", kml.kml())
                st.session_state.kmz_buffer = kmz_buf.getvalue()
                st.success("KMZ Gerado!")
            except Exception as e:
                st.error(f"Erro ao gerar mapa: {e}")

        if st.session_state.kmz_buffer:
            col_btn2.download_button(
                "📥 Baixar KMZ Filtrado", 
                st.session_state.kmz_buffer, 
                "mapa_filtrado.kmz",
                "application/vnd.google-earth.kmz"
            )
