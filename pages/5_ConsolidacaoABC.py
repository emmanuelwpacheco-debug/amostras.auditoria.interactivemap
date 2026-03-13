import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Histórico Consolidado GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico e Unidades Construtivas")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (Siga a ordem BM1, BM2...)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def identificar_coluna(lista_cols, termos):
    """Retorna o nome da coluna que contém um dos termos pesquisados"""
    for col in lista_cols:
        if any(termo in str(col).upper() for termo in termos):
            return col
    return None

if uploaded_files:
    dados_bms = {}
    ordem_bms = []

    for file in uploaded_files:
        try:
            # Lendo a partir da linha 26 (Cabeçalho dos serviços)
            df = pd.read_excel(file, skiprows=25)
            
            # Limpeza de nomes de colunas e remoção de colunas vazias
            df.columns = [str(c).strip().upper() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('UNNAMED|NAN', case=False)]
            
            # Mapeamento Dinâmico (Evita o erro de index out of bounds)
            c_cod  = df.columns[0] # Código é sempre a primeira
            c_serv = df.columns[1] # Serviço é sempre a segunda
            c_unid = identificar_coluna(df.columns, ['UNID'])
            c_precu = identificar_coluna(df.columns, ['PREÇO UNIT', 'UNITÁRIO'])
            c_qtd_orc = identificar_coluna(df.columns, ['CONTRATADA', 'QTD. ORC'])
            
            # Colunas da Medição Atual (Aquelas que se repetem no histórico)
            c_qtd_bm  = identificar_coluna(df.columns, ['DA MEDIÇÃO']) # Quantidade
            # Filtramos a coluna de valor que contenha 'VALOR' e 'MEDIÇÃO'
            c_val_bm = next((c for c in df.columns if 'VALOR' in c and 'MEDIÇÃO' in c), None)
            c_k0     = identificar_coluna(df.columns, ['FATOR', 'K0', '(K)'])
            c_reaj   = identificar_coluna(df.columns, ['REAJUSTE', 'REAJUSTAMENTO'])

            nome_bm = file.name.split('.')[0]
            ordem_bms.append(nome_bm)

            # Criando DataFrame padronizado com as colunas encontradas
            # Se uma coluna opcional (como K0) não for achada, cria com zeros
            cols_map = {
                'COD': c_cod, 'SERVICO': c_serv, 'UNID': c_unid, 
                'PRECO_UNIT': c_precu, 'QTD_ORC': c_qtd_orc,
                'QTD_BM': c_qtd_bm, 'VALOR_BM': c_val_bm, 
                'K0_BM': c_k0, 'REAJ_BM': c_reaj
            }

            df_temp = pd.DataFrame()
            for key, col_name in cols_map.items():
                if col_name and col_name in df.columns:
                    df_temp[key] = df[col_name]
                else:
                    df_temp[key] = 0 # Preenche com 0 se a coluna não existir no arquivo

            # Renomeia as colunas específicas desta medição para o merge
            df_temp = df_temp.rename(columns={
                'QTD_BM': f'QTD_{nome_bm}',
                'VALOR_BM': f'VALOR_{nome_bm}',
                'K0_BM': f'K0_{nome_bm}',
                'REAJ_BM': f'REAJ_{nome_bm}'
            })
            
            # Filtro de segurança: remove linhas onde código e serviço são nulos
            df_temp = df_temp.dropna(subset=['COD', 'SERVICO'], how='all')
            
            dados_bms[nome_bm] = df_temp
            
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_bms:
        # 1. BASE: Pega a estrutura do primeiro arquivo (inclui Unidades Construtivas)
        primeira = ordem_bms[0]
        base_df = dados_bms[primeira][['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']].copy()

        # 2. ADITIVOS: Adiciona novos serviços que possam surgir em BMs posteriores
        for nome in ordem_bms[1:]:
            df_bm = dados_bms[nome]
            novos = df_bm[~df_bm['COD'].isin(base_df['COD'])][['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']]
            base_df = pd.concat([base_df, novos], ignore_index=True)

        # 3. MERGE: Encaixa as colunas de cada medição na base
        resultado = base_df
        for nome in ordem_bms:
            cols_med = ['COD', 'SERVICO', f'QTD_{nome}', f'VALOR_{nome}', f'K0_{nome}', f'REAJ_{nome}']
            resultado = pd.merge(resultado, dados_bms[nome][cols_med], on=['COD', 'SERVICO'], how='left')

        # 4. TOTAIS ACUMULADOS
        resultado = resultado.fillna(0)
        
        c_qtds = [c for c in resultado.columns if 'QTD_' in c and 'ORC' not in c]
        c_vals = [c for c in resultado.columns if 'VALOR_' in c]
        c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

        resultado['QTD_TOTAL_ACUM'] = resultado[c_qtds].sum(axis=1)
        resultado['VALOR_TOTAL_ACUM'] = resultado[c_vals].sum(axis=1)
        resultado['REAJUSTE_TOTAL_ACUM'] = resultado[c_reajs].sum(axis=1)

        # 5. IDENTIFICAÇÃO VISUAL DE UNIDADES CONSTRUTIVAS
        # Conforme seu requisito: Unidades Construtivas têm Preço e Unidade zerados
        def destacar_estilo(row):
            if row['PRECO_UNIT'] == 0 and str(row['UNID']) in ['0', '0.0', 'nan', '']:
                return ['background-color: #e8f4f8; font-weight: bold'] * len(row)
            return [''] * len(row)

        st.subheader("📋 Histórico Consolidado de Medições")
        st.dataframe(resultado.style.apply(destacar_estilo, axis=1), use_container_width=True)

        # Exportação
        output = io.BytesIO()
        resultado.to_excel(output, index=False)
        st.download_button("📥 Baixar Planilha Consolidada", output.getvalue(), "historico_obras_GO.xlsx")

        # CURVA ABC (Apenas o que é serviço real)
        if st.checkbox("Gerar Curva ABC (Excluir Unidades Construtivas)"):
            abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
            abc = abc.sort_values('VALOR_TOTAL_ACUM', ascending=False)
            total = abc['VALOR_TOTAL_ACUM'].sum()
            abc['%_ACUM'] = (abc['VALOR_TOTAL_ACUM'] / total).cumsum() * 100
            st.dataframe(abc[['COD', 'SERVICO', 'VALOR_TOTAL_ACUM', '%_ACUM']], use_container_width=True)
