import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Histórico Consolidado GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico (Estrutura Orçamentária)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições na ordem cronológica (BM1, BM2...)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def identificar_coluna(lista_cols, termos):
    for col in lista_cols:
        if any(termo in str(col).upper() for termo in termos):
            return col
    return None

if uploaded_files:
    # 1. CRIAR O ESQUELETO (Baseado obrigatoriamente no primeiro arquivo)
    try:
        primeiro_arquivo = uploaded_files[0]
        df_base = pd.read_excel(primeiro_arquivo, skiprows=25)
        df_base.columns = [str(c).strip().upper() for c in df_base.columns]
        df_base = df_base.loc[:, ~df_base.columns.str.contains('UNNAMED|NAN', case=False)]
        
        # Identifica as colunas base do orçamento
        c_cod = df_base.columns[0]
        c_serv = df_base.columns[1]
        c_unid = identificar_coluna(df_base.columns, ['UNID'])
        c_precu = identificar_coluna(df_base.columns, ['PREÇO UNIT', 'UNITÁRIO'])
        c_qtd_orc = identificar_coluna(df_base.columns, ['CONTRATADA', 'QTD. ORC'])
        
        # Filtra apenas o essencial e cria um ID de posição para não duplicar grupos
        esqueleto = df_base[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        esqueleto.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        esqueleto['POSICAO_ORIGINAL'] = esqueleto.index # Chave mestra para manter a estrutura
        
        # Limpa linhas totalmente vazias que o Excel às vezes traz no fim
        esqueleto = esqueleto.dropna(subset=['COD', 'SERVICO'], how='all')
        
    except Exception as e:
        st.error(f"Erro ao ler o arquivo base (Orçamento): {e}")
        st.stop()

    # 2. PROCESSAR AS MEDIÇÕES E ENCAIXAR NO ESQUELETO
    resultado = esqueleto.copy()
    ordem_bms = []

    for file in uploaded_files:
        try:
            df_bm = pd.read_excel(file, skiprows=25)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            df_bm = df_bm.loc[:, ~df_bm.columns.str.contains('UNNAMED|NAN', case=False)]
            
            nome_bm = file.name.split('.')[0]
            ordem_bms.append(nome_bm)

            # Mapeia colunas de medição do arquivo atual
            c_qtd_bm = identificar_coluna(df_bm.columns, ['DA MEDIÇÃO'])
            c_val_bm = next((c for c in df_bm.columns if 'VALOR' in c and 'MEDIÇÃO' in c), None)
            c_k0 = identificar_coluna(df_bm.columns, ['FATOR', 'K0', '(K)'])
            c_reaj = identificar_coluna(df_bm.columns, ['REAJUSTE', 'REAJUSTAMENTO'])

            # Criamos um dataframe temporário da medição mantendo o índice original
            # Isso assume que os arquivos de medição seguem a mesma ordem de linhas do orçamento
            medicao_temp = pd.DataFrame(index=df_bm.index)
            medicao_temp[f'QTD_{nome_bm}'] = pd.to_numeric(df_bm[c_qtd_bm], errors='coerce').fillna(0) if c_qtd_bm else 0
            medicao_temp[f'VALOR_{nome_bm}'] = pd.to_numeric(df_bm[c_val_bm], errors='coerce').fillna(0) if c_val_bm else 0
            medicao_temp[f'K0_{nome_bm}'] = df_bm[c_k0] if c_k0 else 1.0
            medicao_temp[f'REAJ_{nome_bm}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0) if c_reaj else 0
            
            # Unimos ao resultado pela posição da linha (index)
            resultado = resultado.join(medicao_temp)
            
        except Exception as e:
            st.warning(f"Erro ao processar medição {file.name}: {e}")

    # 3. CÁLCULOS ACUMULADOS
    resultado = resultado.fillna(0)
    
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_TOTAL_ACUM'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_TOTAL_ACUM'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_TOTAL_ACUM'] = resultado[c_reajs].sum(axis=1)
    resultado['VALOR_GLOBAL_ACUM'] = resultado['VALOR_TOTAL_ACUM'] + resultado['REAJUSTE_TOTAL_ACUM']

    # 4. FORMATAÇÃO E EXIBIÇÃO
    def estilo_hierarquia(row):
        # Unidades Construtivas (Grupos) geralmente não têm unidade física ou preço unitário
        if row['PRECO_UNIT'] == 0 or str(row['UNID']).strip() in ['0', 'nan', '']:
            return ['background-color: #f8f9fa; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    st.subheader("📋 Relatório Consolidado")
    st.info("A estrutura abaixo segue rigorosamente a ordem das linhas do primeiro arquivo enviado.")
    
    # Exibição otimizada (removendo coluna de posição técnica)
    df_display = resultado.drop(columns=['POSICAO_ORIGINAL'])
    st.dataframe(df_display.style.apply(estilo_hierarquia, axis=1), use_container_width=True)

    # Exportação
    output = io.BytesIO()
    resultado.to_excel(output, index=False)
    st.download_button("📥 Baixar Planilha Consolidada", output.getvalue(), "historico_fidedigno_goinfra.xlsx")
