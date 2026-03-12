import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização Rodoviária", layout="wide")

st.title("🏛️ Sistema de Acompanhamento de Fiscalização - GO")
st.markdown("---")

st.markdown("### Painel de Controle de Auditoria")

# Criando o grid de botões
c1, c2, c3 = st.columns(3)

with c1:
    st.info("### 🚧 Amostragem")
    if st.button("Abrir Amostragem", key="btn_amo"):
        st.switch_page("pages/1_amostragem.py")

with c2:
    st.success("### 📸 Geotag Fotos")
    if st.button("Abrir Geotag", key="btn_foto"):
        st.switch_page("pages/2_fotos_georreferenciadas.py")

with c3:
    st.warning("### 🛣️ Diretriz")
    if st.button("Abrir Diretriz", key="btn_dire"):
        st.switch_page("pages/3_DiretrizEstruturada.py")

st.markdown("---")

c4, c5, c6 = st.columns(3)

with c4:
    st.error("### 🗺️ Inventário")
    if st.button("Abrir Inventário", key="btn_inv"):
        st.switch_page("pages/4_InventarioRodoviario.py")

with c5:
    # --- NOVO BOTÃO AQUI ---
    st.help("### 📊 Consolidação ABC")
    st.write("Consolide medições de contratos e gere a Curva ABC.")
    if st.button("Abrir ABC", key="btn_abc"):
        st.switch_page("pages/5_ConsolidacaoABC.py")

with c6:
    st.empty() # Espaço reservado para futuro módulo

st.sidebar.markdown("---")
st.sidebar.caption("Versão 1.5.0 - Auditoria de Contratos")
