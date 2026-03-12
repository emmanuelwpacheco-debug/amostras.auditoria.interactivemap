import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidação e Curva ABC", layout="wide")

st.title("📊 Scanner de Medições e Curva ABC")
st.markdown("Arraste seus arquivos Excel de medição. O sistema ignora o cabeçalho administrativo automaticamente.")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (Excel)", 
    type=['xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    dfs_processados = []
    
    for file in uploaded_files:
        # Lemos a partir da linha 26 (skiprows=25)
        df = pd.read_excel(file, skiprows=25)
        
        # Limpeza básica de colunas
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Remove linhas de subtotais (comum em medições terem linhas "TOTAL DO TRECHO")
        # Geralmente essas linhas não têm código de serviço
        df = df.dropna(subset=[df.columns[0]]) # Assume que a 1ª coluna é o Código
        
        dfs_processados.append(df)
    
    df_unificado = pd.concat(dfs_processados, ignore_index=True)

    # --- AUTO-DETECÇÃO DE COLUNAS ---
    cols = df_unificado.columns.tolist()
    
    def detectar(termos):
        for i, c in enumerate(cols):
            if any(t in c for t in termos): return i
        return 0

    st.subheader("🔍 Conferência de Colunas Detectadas")
    c1, c2, c3, c4 = st.columns(4)
    with c1: col_cod = st.selectbox("Código", cols, index=detectar(['CÓD', 'ITEM']))
    with c2: col_serv = st.selectbox("Descrição", cols, index=detectar(['SERVIÇO', 'DESC']))
    with c3: col_qtd = st.selectbox("Qtd Medida", cols, index=detectar(['DA MEDIÇÃO', 'QTD']))
    with c4: col_prc = st.selectbox("Preço Unitário", cols, index=detectar(['UNITÁRIO', 'PREÇO']))

    if st.button("📈 Gerar Consolidação e ABC"):
        # Conversão numérica
        for c in [col_qtd, col_prc]:
            df_unificado[c] = pd.to_numeric(df_unificado[c], errors='coerce').fillna(0)
        
        # Consolidação por Código
        consolidado = df_unificado.groupby([col_cod, col_serv, col_prc]).agg({
            col_qtd: 'sum'
        }).reset_index()
        
        consolidado['TOTAL_VALOR'] = consolidado[col_qtd] * consolidado[col_prc]
        
        # Geração da ABC
        abc = consolidado.sort_values(by='TOTAL_VALOR', ascending=False).copy()
        total_contrato = abc['TOTAL_VALOR'].sum()
        
        abc['% SIMPLES'] = (abc['TOTAL_VALOR'] / total_contrato) * 100
        abc['% ACUMULADA'] = abc['% SIMPLES'].cumsum()
        abc['CLASSE'] = abc['% ACUMULADA'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

        # Métricas
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Valor Total Acumulado", f"R$ {total_contrato:,.2f}")
        m2.metric("Itens Classe A", len(abc[abc['CLASSE'] == 'A']))
        m3.metric("Representação Classe A", f"{abc[abc['CLASSE'] == 'A']['% SIMPLES'].sum():.1f}%")

        st.dataframe(abc, use_container_width=True)

        # Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            abc.to_excel(writer, sheet_name='Curva ABC', index=False)
            df_unificado.to_excel(writer, sheet_name='Dados Brutos', index=False)
        
        st.download_button("📥 Baixar Relatório Consolidado", output.getvalue(), "ABC_Consolidada.xlsx")
