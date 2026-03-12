import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização Rodoviária", layout="wide")

st.title("🏛️ Sistema de Fiscalização - GO")
st.markdown("---")

# Linha 1
c1, c2, c3 = st.columns(3)
with c1:
    st.info("### 🚧 Amostragem")
    if st.button("Abrir", key="b1"): st.switch_page("pages/1_amostragem.py")
with c2:
    st.success("### 📸 Geotag Fotos")
    if st.button("Abrir", key="b2"): st.switch_page("pages/2_fotos_georreferenciadas.py")
with c3:
    st.warning("### 🛣️ Diretriz")
    if st.button("Abrir", key="b3"): st.switch_page("pages/3_DiretrizEstruturada.py")

st.markdown("---")

# Linha 2
c4, c5 = st.columns(2)
with c4:
    st.error("### 🗺️ Inventário")
    if st.button("Abrir", key="b4"): st.switch_page("pages/4_InventarioRodoviario.py")
with c5:
    st.help("### 📊 Consolidação ABC")
    # O comando abaixo deve bater EXATAMENTE com o nome do arquivo na pasta pages
    if st.button("Abrir", key="b5"): st.switch_page("pages/5_ConsolidacaoABC.py")
