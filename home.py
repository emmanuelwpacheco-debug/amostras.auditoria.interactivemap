import streamlit as st

st.set_page_config(page_title="Fiscalizacao GO", layout="wide")

st.title("🏛️ Sistema de Fiscalização - GO")
st.divider()

# Grid de Navegação
c1, c2, c3 = st.columns(3)

with c1:
    st.info("### 🚧 Amostragem")
    if st.button("Abrir", key="btn1"):
        st.switch_page("pages/1_amostragem.py")

with c2:
    st.success("### 📸 Geotag Fotos")
    if st.button("Abrir", key="btn2"):
        st.switch_page("pages/2_fotos_georreferenciadas.py")

with c3:
    st.warning("### 🛣️ Diretriz")
    if st.button("Abrir", key="btn3"):
        st.switch_page("pages/3_DiretrizEstruturada.py")

st.divider()

c4, c5 = st.columns(2)

with c4:
    st.error("### 🗺️ Inventário")
    if st.button("Abrir", key="btn4"):
        st.switch_page("pages/4_InventarioRodoviario.py")

with c5:
    st.help("### 📊 Consolidação ABC")
    if st.button("Abrir", key="btn5"):
        st.switch_page("pages/5_ConsolidacaoABC.py")
