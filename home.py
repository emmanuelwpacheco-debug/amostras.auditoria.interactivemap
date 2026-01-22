import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização Rodoviária", layout="wide")

st.title("🏛️ Sistema de Acompanhamento de Fiscalização de obras rodoviárias")
st.markdown("---")

st.markdown("""
### Bem-vindo, Auditor!
Este sistema centraliza as ferramentas de apoio à fiscalização de obras rodoviárias.
Utilize o menu ao lado para navegar entre os módulos disponíveis.
""")

# Criando Cards de atalho na Home
col1, col2 = st.columns(2)

with col1:
    st.info("### 🚧 Amostragem de Campo")
    st.write("Geração de pontos aleatórios de coleta seguindo critérios do IBRAOP")
    if st.button("Abrir Módulo de Amostragem"):
        st.switch_page("pages/1_amostragem.py") # Comando para saltar de página

with col2:
    st.success("### 📊 Relatórios de Auditoria")
    st.write("Módulo em desenvolvimento para consolidação de ensaios e medições.")
    if st.button("Ver Status", disabled=True):
        pass

st.sidebar.markdown("---")
st.sidebar.caption("Versão 1.0.0 - Gestão de Ativos")
