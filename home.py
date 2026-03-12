import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização Rodoviária", layout="wide")

# Estilização básica para remover o erro visual
st.title("🏛️ Sistema de Acompanhamento de Fiscalização - GO")
st.markdown("---")

st.subheader("🛠️ Módulos de Auditoria e Fiscalização")

# Organização em Grid (Linha 1)
c1, c2, c3 = st.columns(3)

with c1:
    st.info("### 🚧 Amostragem")
    st.write("Cálculo de amostragem para ensaios.")
    if st.button("Abrir Amostragem", key="btn_amo"):
        st.switch_page("pages/1_amostragem.py")

with c2:
    st.success("### 📸 Geotag Fotos")
    st.write("Extração de coordenadas de fotos.")
    if st.button("Abrir Geotag", key="btn_foto"):
        st.switch_page("pages/2_fotos_georreferenciadas.py")

with c3:
    st.warning("### 🛣️ Diretriz")
    st.write("Análise de diretrizes estruturadas.")
    if st.button("Abrir Diretriz", key="btn_dire"):
        st.switch_page("pages/3_DiretrizEstruturada.py")

st.markdown("---")

# Organização em Grid (Linha 2)
c4, c5, c6 = st.columns(3)

with c4:
    st.error("### 🗺️ Inventário")
    st.write("Filtro de revestimento e mapas KMZ.")
    if st.button("Abrir Inventário", key="btn_inv"):
        st.switch_page("pages/4_InventarioRodoviario.py")

with c5:
    st.help("### 📊 Consolidação ABC")
    st.write("Consolidação de medições (Excel) e Curva ABC.")
    if st.button("Abrir ABC", key="btn_abc"):
        # Certifique-se que o arquivo abaixo existe na pasta pages/
        try:
            st.switch_page("pages/5_ConsolidacaoABC.py")
        except:
            st.error("Arquivo pages/5_ConsolidacaoABC.py não encontrado.")

with c6:
    st.empty() # Espaço livre

st.sidebar.markdown("---")
st.sidebar.caption("Versão 2.0 - Foco em Celeridade")
