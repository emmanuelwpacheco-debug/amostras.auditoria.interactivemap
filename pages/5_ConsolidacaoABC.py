import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidacao GOINFRA", layout="wide")
st.title("📊 Consolidação Sequencial e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    dados_por_arquivo = {}
    
    for file in uploaded_files:
        try:
            # Leitura robusta: ignora as 25 linhas de cabeçalho administrativo
            df = pd.read_excel(file, skiprows=25)
            
            # 1. Limpeza de colunas: remove vazias e converte tudo para string limpa
            df.columns = [str(c).strip() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('Unnamed|nan', case=False)]
            
            # 2. Filtro: Mantém apenas linhas que tenham o código do serviço (coluna 0)
            df = df.dropna(subset=[df.columns[0]])
            
            if not df.empty:
                nome_med = file.name.replace('.xls', '').replace('.xlsx', '')
                dados_por_arquivo[nome_med] = df
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_por_arquivo:
        # Pega a lista de colunas do primeiro arquivo para mapeamento
        exemplo_df = list(dados_por_arquivo.values())[0]
        cols = exemplo_df.columns.tolist()

        st.subheader("⚙️ Ajuste de Mapeamento")
        c1, c2, c3, c4 = st.columns(4)
        with c1: col_id = st.selectbox("Cód. Serviço", cols, index=0)
        with c2: col_desc = st.selectbox("Descrição", cols, index=1 if len(cols)>1 else 0)
        with c3: col_qtd = st.selectbox("Qtd Medição", cols, index=len(cols)-3 if len(cols)>3 else 0)
        with c4: col_val = st.selectbox("Valor Medição", cols, index=len(cols)-2 if len(cols)>2 else 0)

        if st.button("🚀 Gerar Consolidação"):
            # Lista para o merge final
            tabelas_limpas = []
            
            for nome, df in dados_por_arquivo.items():
                # Extrai apenas as colunas necessárias e renomeia com o nome da medição
                temp = df[[col_id, col_desc, col_qtd, col_val]].copy()
                
                # Converte valores para número (forçado)
                temp[col_qtd] = pd.to_numeric(temp[col_qtd], errors='coerce').fillna(0)
                temp[col_val] = pd.to_numeric(temp[col_val], errors='coerce').fillna(0)
                
                # Renomeia para identificar a medição (Ex: Qtd_BM01, Valor_BM01)
                temp = temp.rename(columns={
                    col_qtd: f"Qtd_{nome}",
                    col_val: f"Valor_{nome}"
                })
                tabelas_limpas.append(temp)

            # --- CONSOLIDAÇÃO SEQUENCIAL (Lado a Lado) ---
            # Faz o merge de todos os arquivos baseados no Código e Descrição
            df_consolidado = tabelas_limpas[0]
            for i in range(1, len(tabelas_limpas)):
                df_consolidado = pd.merge(
                    df_consolidado, 
                    tabelas_limpas[i], 
                    on=[col_id, col_desc], 
                    how='outer'
                ).fillna(0)

            # Cálculo do Acumulado (Soma horizontal das colunas de valor)
            cols_valor = [c for c in df_consolidado.columns if 'Valor_' in c]
            df_consolidado['VALOR_ACUMULADO'] = df_consolidado[cols_valor].sum(axis=1)

            # --- EXIBIÇÃO ---
            st.divider()
            st.subheader("📋 Tabela Sequencial de Medições")
            st.dataframe(df_consolidado, use_container_width=True)

            # --- CURVA ABC ---
            abc = df_consolidado[df_consolidado['VALOR_ACUMULADO'] > 0].copy()
            abc = abc.sort_values(by='VALOR_ACUMULADO', ascending=False)
            
            total_geral = abc['VALOR_ACUMULADO'].sum()
            abc['%_SIMPLES'] = (abc['VALOR_ACUMULADO'] / total_geral) * 100
            abc['%_ACUM'] = abc['%_SIMPLES'].cumsum()
            abc['CLASSE'] = abc['%_ACUM'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

            st.subheader("🏆 Curva ABC (Baseada no Acumulado)")
            st.metric("Total Geral Medido", f"R$ {total_geral:,.2f}")
            st.dataframe(abc[[col_id, col_desc, 'VALOR_ACUMULADO', '%_ACUM', 'CLASSE']], use_container_width=True)

            # Exportação
            output = io.BytesIO()
            df_consolidado.to_excel(output, index=False)
            st.download_button("📥 Baixar Planilha Consolidada", output.getvalue(), "consolidacao_goinfra.xlsx")
