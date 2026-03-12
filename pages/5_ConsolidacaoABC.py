import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidação e Curva ABC", layout="wide")

st.title("📊 Scanner de Medições e Curva ABC")

# AJUSTE: Agora aceita .xlsx e .xls
uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (Excel)", 
    type=['xlsx', 'xls'], 
    accept_multiple_files=True
)

if uploaded_files:
    dfs_processados = []
    
    for file in uploaded_files:
        try:
            # Tenta ler pulando as 25 linhas de cabeçalho administrativo
            df = pd.read_excel(file, skiprows=25)
            
            # Limpa nomes das colunas de espaços e quebras de linha
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            # Remove linhas que não possuem código de serviço (geralmente lixo ou subtotais)
            if len(df.columns) > 0:
                df = df.dropna(subset=[df.columns[0]])
                dfs_processados.append(df)
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")
    
    if dfs_processados:
        df_unificado = pd.concat(dfs_processados, ignore_index=True)
        st.success(f"{len(dfs_processados)} arquivos processados!")

        # Mapeamento dinâmico
        cols = df_unificado.columns.tolist()
        c1, c2, c3, c4 = st.columns(4)
        with c1: col_cod = st.selectbox("Código", cols, index=0)
        with c2: col_serv = st.selectbox("Serviço", cols, index=1 if len(cols)>1 else 0)
        with c3: col_qtd = st.selectbox("Qtd Medição", cols, index=6 if len(cols)>6 else 0)
        with c4: col_prc = st.selectbox("Valor Unitário", cols, index=4 if len(cols)>4 else 0)

        if st.button("📈 Gerar Curva ABC"):
            # Conversão e Cálculo
            df_unificado[col_qtd] = pd.to_numeric(df_unificado[col_qtd], errors='coerce').fillna(0)
            df_unificado[col_prc] = pd.to_numeric(df_unificado[col_prc], errors='coerce').fillna(0)
            
            # Agrupa por código e serviço
            abc = df_unificado.groupby([col_cod, col_serv, col_prc]).agg({col_qtd: 'sum'}).reset_index()
            abc['TOTAL'] = abc[col_qtd] * abc[col_prc]
            abc = abc[abc['TOTAL'] > 0].sort_values(by='TOTAL', ascending=False)
            
            # Lógica ABC
            total_geral = abc['TOTAL'].sum()
            abc['%_ACUM'] = (abc['TOTAL'] / total_geral).cumsum() * 100
            abc['CLASSE'] = abc['%_ACUM'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

            st.metric("Valor Total Consolidado", f"R$ {total_geral:,.2f}")
            st.dataframe(abc, use_container_width=True)
