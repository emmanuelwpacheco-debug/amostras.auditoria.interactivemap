import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Histórico de Medições GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico Acumulado (Orçamento + Aditivos)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (Siga a ordem cronológica: BM1, BM2...)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def formatar_colunas(df):
    """Limpa nomes de colunas para evitar erros de busca"""
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df.loc[:, ~df.columns.str.contains('UNNAMED|NAN', case=False)]

if uploaded_files:
    dados_bms = {}
    ordem_arquivos = []

    for file in uploaded_files:
        try:
            # Leitura padrão GOINFRA
            df = pd.read_excel(file, skiprows=25)
            df = formatar_colunas(df)
            
            nome_bm = file.name.split('.')[0]
            ordem_arquivos.append(nome_bm)
            
            # Mapeamento manual para evitar o erro '[None] not in index'
            # Se não achar o nome exato, pegamos pela posição (mais seguro)
            col_cod = df.columns[0]
            col_serv = df.columns[1]
            col_unid = df.columns[2]
            col_precu = df.columns[3]
            col_qtd_orc = df.columns[4]
            
            # Procurando as colunas de medição (geralmente as últimas)
            # Buscamos palavras-chave para ser flexível
            col_qtd_med = next((c for c in df.columns if "DA MEDIÇÃO" in c and "VALOR" not in c), df.columns[5])
            col_val_med = next((c for c in df.columns if "DA MEDIÇÃO" in c and "VALOR" in c), df.columns[8])
            col_k0 = next((c for c in df.columns if "FATOR(K)" in c or "K0" in c), df.columns[10])
            col_reaj = next((c for c in df.columns if "REAJUSTE" in c), df.columns[11])

            # Criando DataFrame padronizado para esta BM
            df_temp = df[[col_cod, col_serv, col_unid, col_precu, col_qtd_orc, col_qtd_med, col_val_med, col_k0, col_reaj]].copy()
            df_temp.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC', 
                               f'QTD_{nome_bm}', f'VALOR_{nome_bm}', f'K0_{nome_bm}', f'REAJ_{nome_bm}']
            
            dados_bms[nome_bm] = df_temp
            
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_bms:
        # 1. CONSTRUÇÃO DA BASE (ORÇAMENTO)
        # Usamos o primeiro arquivo como referência de estrutura (inclusive títulos)
        primeira_bm = ordem_arquivos[0]
        base_df = dados_bms[primeira_bm][['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']].copy()

        # 2. ADIÇÃO DE ITENS DE ADITIVOS (Sincronização)
        for nome in ordem_arquivos[1:]:
            df_atual = dados_bms[nome]
            # Verifica se existem códigos novos que não estão na base
            novos_itens = df_atual[~df_atual['COD'].isin(base_df['COD'])][['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']]
            if not novos_itens.empty:
                base_df = pd.concat([base_df, novos_itens], ignore_index=True)

        # 3. MERGE DOS VALORES DE CADA BM
        resultado_final = base_df
        for nome in ordem_arquivos:
            cols_interesse = ['COD', 'SERVICO', f'QTD_{nome}', f'VALOR_{nome}', f'K0_{nome}', f'REAJ_{nome}']
            resultado_final = pd.merge(resultado_final, dados_bms[nome][cols_interesse], on=['COD', 'SERVICO'], how='left')

        # 4. CÁLCULO DOS ACUMULADOS
        resultado_final = resultado_final.fillna(0)
        
        c_qtds = [c for c in resultado_final.columns if 'QTD_' in c and 'ORC' not in c]
        c_vals = [c for c in resultado_final.columns if 'VALOR_' in c]
        c_reajs = [c for c in resultado_final.columns if 'REAJ_' in c]

        resultado_final['QTD_ACUMULADA'] = resultado_final[c_qtds].sum(axis=1)
        resultado_final['VALOR_ACUMULADO'] = resultado_final[c_vals].sum(axis=1)
        resultado_final['VALOR_REAJUSTE_ACUMULADO'] = resultado_final[c_reajs].sum(axis=1)

        # --- EXIBIÇÃO ---
        st.subheader("📋 Histórico Consolidado (Estrutura Completa)")
        st.write("Linhas sem Unidade e Preço são tratadas como Unidades Construtivas (Grupos).")
        
        # Mostra a tabela (usando estilo para facilitar leitura de grupos)
        def highlight_groups(s):
            return ['background-color: #f0f2f6; font-weight: bold' if s.UNID == 0 else '' for _ in s]

        st.dataframe(resultado_final, use_container_width=True)

        # Exportação
        output = io.BytesIO()
        resultado_final.to_excel(output, index=False)
        st.download_button("📥 Baixar Planilha de Histórico", output.getvalue(), "historico_consolidado.xlsx")

        # --- CURVA ABC (Apenas Serviços) ---
        if st.checkbox("Ver Curva ABC do Acumulado (Exclui Grupos)"):
            abc = resultado_final[resultado_final['PRECO_UNIT'] > 0].copy()
            abc = abc.sort_values('VALOR_ACUMULADO', ascending=False)
            total = abc['VALOR_ACUMULADO'].sum()
            abc['%_ACUM'] = (abc['VALOR_ACUMULADO'] / total).cumsum() * 100
            st.dataframe(abc[['COD', 'SERVICO', 'VALOR_ACUMULADO', '%_ACUM']], use_container_width=True)
