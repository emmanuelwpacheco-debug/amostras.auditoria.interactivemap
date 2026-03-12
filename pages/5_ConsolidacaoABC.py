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
            
            # --- CORREÇÃO DO ERRO AQUI ---
            # 1. Converte todos os nomes de colunas para string (evita o erro do 'float')
            temp_df.columns = [str(c) for c in temp_df.columns]
            
            # 2. Agora sim remove as colunas "Unnamed" ou vazias com segurança
            temp_df = temp_df.loc[:, ~temp_df.columns.str.contains('Unnamed|nan', case=False)]
            
            # 3. Limpa espaços nos nomes das colunas restantes
            temp_df.columns = [c.strip() for c in temp_df.columns]
            
            # Filtra apenas linhas que possuem código de serviço (primeira coluna)
            if not temp_df.empty:
                col_primaria = temp_df.columns[0]
                temp_df = temp_df.dropna(subset=[col_primaria])
                dfs.append(temp_df)
                
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")

    if dfs:
        df_total = pd.concat(dfs, ignore_index=True)
        cols = df_total.columns.tolist()

        st.subheader("⚙️ Verifique o Mapeamento - O programa lê a planilha mas está sujeito a erros. Assim, criamos as colunas para o usuário conferir se o Python pegou os nomes certos. ")
        # Criamos as colunas para o usuário conferir se o Python pegou os nomes certos
        c1, c2, c3, c4 = st.columns(4)
        
        with c1: c_id = st.selectbox("Cód. Serviço", cols, index=0)
        with c2: c_desc = st.selectbox("Descrição", cols, index=1 if len(cols)>1 else 0)
        with c3: c_qtd = st.selectbox("Qtd Medição", cols, index=len(cols)-2 if len(cols)>2 else 0)
        with c4: c_uni = st.selectbox("Preço Unitário", cols, index=len(cols)-4 if len(cols)>4 else 0)
        
        if st.button("📈 Gerar Relatório Consolidado"):
            # Conversão forçada para números
            df_total[c_qtd] = pd.to_numeric(df_total[c_qtd], errors='coerce').fillna(0)
            df_total[c_uni] = pd.to_numeric(df_total[c_uni], errors='coerce').fillna(0)
            
            # Agrupamento e cálculo
            resumo = df_total.groupby([c_id, c_desc, c_uni]).agg({c_qtd: 'sum'}).reset_index()
            resumo['VALOR TOTAL'] = resumo[c_qtd] * resumo[c_uni]
            
            # Ordenação Curva ABC
            abc = resumo[resumo['VALOR TOTAL'] > 0.01].sort_values('VALOR TOTAL', ascending=False)
            
            if not abc.empty:
                total_geral = abc['VALOR TOTAL'].sum()
                abc['% ACUM'] = (abc['VALOR TOTAL'] / total_geral).cumsum() * 100
                abc['CLASSE'] = abc['% ACUM'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

                st.divider()
                st.metric("Total das Medições", f"R$ {total_geral:,.2f}")
                st.dataframe(abc.style.format({c_uni: "{:.2f}", 'VALOR TOTAL': "{:.2f}", '% ACUM': "{:.2f}%"}), use_container_width=True)
                
                # Exportação
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    abc.to_excel(writer, index=False, sheet_name='ABC')
                st.download_button("📥 Baixar Excel Consolidado", output.getvalue(), "curva_abc_consolidada.xlsx")
            else:
                st.warning("Verifique se as colunas de Quantidade e Preço Unitário estão selecionadas corretamente.")
