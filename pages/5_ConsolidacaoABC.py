import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidação ABC", layout="wide")
st.title("📊 Scanner de Medições - GOINFRA")

uploaded_files = st.sidebar.file_uploader("Carregue os arquivos .xls", type=['xls', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    dfs = []
    for file in uploaded_files:
        try:
            # Lê o arquivo ignorando o topo administrativo
            temp_df = pd.read_excel(file, skiprows=25)
            
            # REMOVE COLUNAS SEM NOME (comuns em células mescladas)
            temp_df = temp_df.loc[:, ~temp_df.columns.str.contains('^Unnamed')]
            
            # Limpa espaços nos nomes das colunas
            temp_df.columns = [str(c).strip() for c in temp_df.columns]
            
            # Filtra apenas linhas que possuem código de serviço
            col_primaria = temp_df.columns[0]
            temp_df = temp_df.dropna(subset=[col_primaria])
            
            dfs.append(temp_df)
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")

    if dfs:
        df_total = pd.concat(dfs, ignore_index=True)
        cols = df_total.columns.tolist()

        st.subheader("⚙️ Verifique o Mapeamento")
        c1, c2, c3, c4 = st.columns(4)
        
        # Seleção manual garantida
        with c1: c_id = st.selectbox("Cód. Serviço", cols, index=0)
        with c2: c_desc = st.selectbox("Descrição", cols, index=1 if len(cols)>1 else 0)
        with c3: c_qtd = st.selectbox("Qtd Medição", cols, index=6 if len(cols)>6 else 0)
        with c4: c_uni = st.selectbox("Preço Unitário", cols, index=4 if len(cols)>4 else 0)

        if st.button("📈 Gerar Relatório Consolidado"):
            # Força a conversão para número, removendo o que não for valor
            df_total[c_qtd] = pd.to_numeric(df_total[c_qtd], errors='coerce').fillna(0)
            df_total[c_uni] = pd.to_numeric(df_total[c_uni], errors='coerce').fillna(0)
            
            # Agrupamento
            resumo = df_total.groupby([c_id, c_desc, c_uni]).agg({c_qtd: 'sum'}).reset_index()
            resumo['TOTAL'] = resumo[c_qtd] * resumo[c_uni]
            
            # Filtra lixo (valores zerados) e ordena
            abc = resumo[resumo['TOTAL'] > 0.01].sort_values('TOTAL', ascending=False)
            
            if not abc.empty:
                total_geral = abc['TOTAL'].sum()
                abc['% ACUM'] = (abc['TOTAL'] / total_geral).cumsum() * 100
                abc['CLASSE'] = abc['% ACUM'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

                st.metric("Total das Medições", f"R$ {total_geral:,.2f}")
                st.dataframe(abc, use_container_width=True)
                
                # Exportação
                output = io.BytesIO()
                abc.to_excel(output, index=False)
                st.download_button("📥 Baixar Excel", output.getvalue(), "curva_abc_consolidada.xlsx")
            else:
                st.warning("Nenhum dado válido encontrado. Verifique se as colunas selecionadas contêm valores numéricos.")
