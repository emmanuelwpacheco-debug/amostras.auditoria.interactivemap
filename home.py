import streamlit as st

st.set_page_config(page_title="Sistema de Fiscalização Rodoviária", layout="wide")

st.title("🏛️ Sistema de Acompanhamento de Fiscalização de obras rodoviárias")
st.markdown("---")

st.markdown("""
### Bem-vinda, Auditora! / Bem-vindo, Auditor!
Este sistema centraliza as ferramentas de apoio à fiscalização de obras rodoviárias.
Utilize o menu ao lado ou os cartões abaixo para navegar entre os módulos disponíveis.
""")

# Criando a malha de colunas para os cartões
col1, col2 = st.columns(2)

with col1:
    st.info("### 🚧 Amostragem de Campo")
    st.write("Geração de pontos aleatórios de coleta seguindo critérios do IBRAOP e análise de curvas.")
    if st.button("Abrir Módulo de Amostragem"):
        st.switch_page("pages/1_amostragem.py")

with col2:
    st.success("### 📸 Geotag de Fotos")
    st.write("Sincronize fotos de inspeção com arquivos GPX para gerar KMZs com imagens embutidas.")
    if st.button("Abrir Módulo de Fotos"):
        st.switch_page("pages/2_fotos_georreferenciadas.py")

st.markdown("---")

# Nova linha de colunas para o terceiro módulo
col3, col4 = st.columns(2)

with col3:
    st.warning("### 🛣️ Diretriz Estruturada")
    st.write("Extração de coordenadas UTM e cotas de projeto a partir de tabelas em PDF para geração de KML 3D.")
    if st.button("Abrir Diretriz Estruturada"):
        st.switch_page("pages/3_DiretrizEstruturada.py")

with col4:
    st.help("### 📊 Relatórios de Auditoria")
    st.write("Módulo em desenvolvimento para consolidação de ensaios e medições automatizadas.")
    if st.button("Ver Status", disabled=True):
        pass

st.sidebar.markdown("---")
st.sidebar.caption("Versão 1.2.0 - Gestão de Ativos")
