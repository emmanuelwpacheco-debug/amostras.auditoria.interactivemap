import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização", layout="wide")

st.title("🏛️ Sistema de Auditoria Rodoviária")
st.markdown("---")

# Layout em colunas
c1, c2 = st.columns(2)

with c1:
    st.subheader("🛣️ Diretriz de Projeto")
    if st.button("Abrir Diretriz", key="btn_dire"):
        st.switch_page("pages/3_DiretrizEstruturada.py")

with c2:
    st.subheader("🚧 Amostragem")
    if st.button("Abrir Amostragem", key="btn_amo"):
        st.switch_page("pages/1_amostragem.py")

st.markdown("---")

c3, c4 = st.columns(2)

with c3:
    st.subheader("📸 Fotos Geotag")
    if st.button("Abrir Fotos", key="btn_foto"):
        st.switch_page("pages/2_fotos_georreferenciadas.py")

with c4:
    st.subheader("📊 Relatórios")
    st.button("Em breve", disabled=True, key="btn_rel")
