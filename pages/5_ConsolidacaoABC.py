import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidação e Curva ABC", layout="wide")
st.title("📊 Consolidação de Medições e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    lista_consolidada = []
    
    for file in uploaded_files:
        try:
            # Leitura ignorando o cabeçalho GOINFRA
            df = pd.read_excel(file, skiprows=25)
            
            # Limpeza de nomes de colunas
            df.columns = [str(c).strip() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('Unnamed|nan', case=False)]
            
            # Remove linhas sem código de serviço
            df = df.dropna(subset=[df.columns[0]])
            
            if not df.empty:
                # Adicionamos o nome do arquivo para o usuário identificar
                df['MEDICAO_FONTE'] = file.name.replace('.xls', '').replace('.xlsx', '')
                lista_consolidada.append(df)
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")

    if lista_consolidada:
        # Unificamos tudo para permitir a seleção de colunas
        df_bruto = pd.concat(lista_consolidada, ignore_index=True)
        cols = df_bruto.columns.tolist()

        st.subheader("⚙️ Configuração do Relatório")
        st.info("Selecione as colunas correspondentes de uma das planilhas carregadas:")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: col_cod = st.selectbox("Código do Serviço", cols, index=0)
        with c2: col_serv = st.selectbox("Descrição/Serviço", cols, index=1 if len(cols)>1 else 0)
        with c3: col_qtd = st.selectbox("Coluna de Quantidade (Medição)", cols, index=len(cols)-3 if len(cols)>3 else 0)
        with c4: col_val = st.selectbox("Coluna de Valor (Medição)", cols, index=len(cols)-2 if len(cols)>2 else 0)

        if st.button("🚀 Gerar Consolidação e ABC"):
            try:
                # 1. Criar a Tabela Sequencial (Pivot Table)
                # Queremos ver: Código, Serviço e as quantidades/valores de cada arquivo
                
                # Convertendo para numérico antes de agrupar
                df_bruto[col_qtd] = pd.to_numeric(df_bruto[col_qtd], errors='coerce').fillna(0)
                df_bruto[col_val] = pd.to_numeric(df_bruto[col_val], errors='coerce').fillna(0)

                # Criando a consolidação lado a lado
                pivot_qtd = df_bruto.pivot_table(
                    index=[col_cod, col_serv], 
                    columns='MEDICAO_FONTE', 
                    values=col_qtd, 
                    aggfunc='sum'
                ).reset_index()
                
                # Renomeando colunas para clareza
                pivot_qtd.columns = [f"QTD_{c}" if c not in [col_cod, col_serv] else c for c in pivot_qtd.columns]

                pivot_val = df_bruto.pivot_table(
                    index=[col_cod, col_serv], 
                    columns='MEDICAO_FONTE', 
                    values=col_val, 
                    aggfunc='sum'
                ).reset_index()
                
                pivot_val.columns = [f"VALOR_{c}" if c not in [col_cod, col_serv] else c for c in pivot_val.columns]

                # Mesclando as duas visões
                df_final = pd.merge(pivot_qtd, pivot_val, on=[col_cod, col_serv])
                
                # Totais Acumulados
                colunas_qtd = [c for c in df_final.columns if 'QTD_' in c]
                colunas_val = [c for c in df_final.columns if 'VALOR_' in c]
                
                df_final['TOTAL_QUANTIDADE'] = df_final[colunas_qtd].sum(axis=1)
                df_final['TOTAL_FINANCEIRO'] = df_final[colunas_val].sum(axis=1)

                # --- EXIBIÇÃO ---
                st.divider()
                st.subheader("📋 Consolidação Sequencial")
                st.dataframe(df_final, use_container_width=True)

                # --- CURVA ABC ---
                abc = df_final[df_final['TOTAL_FINANCEIRO'] > 0.01].copy()
                abc = abc.sort_values(by='TOTAL_FINANCEIRO', ascending=False)
                
                total_geral = abc['TOTAL_
