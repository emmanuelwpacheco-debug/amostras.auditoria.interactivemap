import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Histórico Consolidado GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico (Correção de Valores)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições na ordem cronológica (BM1, BM2...)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def identificar_colunas_medicao(df):
    """
    Busca especificamente as colunas de Quantidade e Valor da Medição
    considerando que ambas podem ter nomes parecidos.
    """
    cols = df.columns.tolist()
    c_qtd, c_val = None, None
    
    # Procura as colunas que contêm 'DA MEDIÇÃO'
    possiveis = [c for c in cols if 'DA MEDIÇÃO' in str(c).upper()]
    
    for p in possiveis:
        # Geralmente a planilha GOINFRA coloca a Qtd antes do Valor
        # ou diferencia por palavras chave no cabeçalho original
        # Se houver duas colunas 'DA MEDIÇÃO', a primeira é Qtd e a segunda é Valor
        # Mas vamos testar o tipo de dado predominante na coluna
        amostra = df[p].dropna().head(10)
        # Se for a coluna de valor, geralmente tem valores maiores ou decimais de moeda
        if c_qtd is None:
            c_qtd = p
        else:
            c_val = p
            
    return c_qtd, c_val

if uploaded_files:
    try:
        # 1. ESQUELETO (Orçamento Base)
        primeiro = uploaded_files[0]
        df_base = pd.read_excel(primeiro, skiprows=25)
        df_base.columns = [str(c).strip().upper() for c in df_base.columns]
        df_base = df_base.loc[:, ~df_base.columns.str.contains('UNNAMED|NAN', case=False)]
        
        # Colunas Fixas
        c_cod = df_base.columns[0]
        c_serv = df_base.columns[1]
        c_unid = next((c for c in df_base.columns if 'UNID' in c), df_base.columns[2])
        c_precu = next((c for c in df_base.columns if 'UNIT' in c), df_base.columns[3])
        c_qtd_orc = next((c for c in df_base.columns if 'CONTRATADA' in c or 'QTD. ORC' in c), df_base.columns[4])
        
        resultado = df_base[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
    except Exception as e:
        st.error(f"Erro ao montar esqueleto: {e}")
        st.stop()

    # 2. PROCESSAMENTO DAS BMs
    for file in uploaded_files:
        try:
            df_bm = pd.read_excel(file, skiprows=25)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            
            nome_bm = file.name.split('.')[0]
            
            # Localização manual precisa das colunas 'DA MEDIÇÃO'
            # Na GOINFRA: Coluna 6 aprox é Qtd, Coluna 9 aprox é Valor (índices 5 e 8)
            # Vamos usar uma lógica de exclusão:
            cols_da_medicao = [i for i, c in enumerate(df_bm.columns) if 'DA MEDIÇÃO' in c]
            
            if len(cols_da_medicao) >= 2:
                idx_qtd = cols_da_medicao[0]
                idx_val = cols_da_medicao[1]
            else:
                # Caso as colunas tenham nomes diferentes
                idx_qtd = 5 # Posição padrão Qtd
                idx_val = 8 # Posição padrão Valor
            
            c_k0 = next((i for i, c in enumerate(df_bm.columns) if 'FATOR' in c or 'K0' in c), 10)
            c_reaj = next((i for i, c in enumerate(df_bm.columns) if 'REAJUSTE' in c), 11)

            # Extração forçada pelos índices das colunas detectadas
            med_temp = pd.DataFrame(index=df_bm.index)
            med_temp[f'QTD_{nome_bm}'] = pd.to_numeric(df_bm.iloc[:, idx_qtd], errors='coerce').fillna(0)
            med_temp[f'VALOR_{nome_bm}'] = pd.to_numeric(df_bm.iloc[:, idx_val], errors='coerce').fillna(0)
            med_temp[f'K0_{nome_bm}'] = df_bm.iloc[:, c_k0].fillna(1.0)
            med_temp[f'REAJ_{nome_bm}'] = pd.to_numeric(df_bm.iloc[:, c_reaj], errors='coerce').fillna(0)
            
            resultado = resultado.join(med_temp)
            
        except Exception as e:
            st.warning(f"Atenção no arquivo {file.name}: {e}")

    # 3. CONSOLIDAÇÃO FINAL
    resultado = resultado.fillna(0)
    
    # Somatórios
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['VALOR_GLOBAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Estilização para Unidades Construtivas
    def style_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.subheader("✅ Histórico Consolidado (Valores Corrigidos)")
    st.dataframe(resultado.style.apply(style_rows, axis=1), use_container_width=True)
    
    # Download
    output = io.BytesIO()
    resultado.to_excel(output, index=False)
    st.download_button("📥 Baixar Planilha Consolidada", output.getvalue(), "historico_finedigno_v2.xlsx")
