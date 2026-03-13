import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Histórico Consolidado GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico (Correção Total de Soma)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições na ordem cronológica (BM1, BM2...)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    try:
        # 1. ESQUELETO (Orçamento Base - Primeiro Arquivo)
        primeiro = uploaded_files[0]
        df_base = pd.read_excel(primeiro, skiprows=25)
        df_base.columns = [str(c).strip().upper() for c in df_base.columns]
        df_base = df_base.loc[:, ~df_base.columns.str.contains('UNNAMED|NAN', case=False)]
        
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
            
            # --- LÓGICA DE CAPTURA DE COLUNAS POR NOME ---
            # Identifica todas as colunas "DA MEDIÇÃO"
            cols_medicao = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            
            # Identifica a coluna de Reajuste (procurando o termo exato ou parcial)
            col_reajuste_nome = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            col_k0_nome = next((c for c in df_bm.columns if 'K0' in c or 'FATOR' in c or '(K)' in c), None)

            med_temp = pd.DataFrame(index=df_bm.index)

            # Quantidade (Normalmente a primeira "Da Medição")
            if len(cols_medicao) >= 1:
                med_temp[f'QTD_{nome_bm}'] = pd.to_numeric(df_bm[cols_medicao[0]], errors='coerce').fillna(0)
            
            # Valor (Normalmente a segunda "Da Medição")
            if len(cols_medicao) >= 2:
                med_temp[f'VALOR_{nome_bm}'] = pd.to_numeric(df_bm[cols_medicao[1]], errors='coerce').fillna(0)
            
            # Reajustamento (Busca pelo nome identificado)
            if col_reajuste_nome:
                med_temp[f'REAJ_{nome_bm}'] = pd.to_numeric(df_bm[col_reajuste_nome], errors='coerce').fillna(0)
            else:
                med_temp[f'REAJ_{nome_bm}'] = 0.0

            # Fator K0
            if col_k0_nome:
                med_temp[f'K0_{nome_bm}'] = df_bm[col_k0_nome].fillna(1.0)
            
            # Unir ao resultado principal
            resultado = resultado.join(med_temp)
            
        except Exception as e:
            st.warning(f"Atenção no arquivo {file.name}: {e}")

    # 3. CONSOLIDAÇÃO FINAL E SOMAS
    resultado = resultado.fillna(0)
    
    # Listar colunas para soma
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    # Somas Acumuladas
    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    
    # VALOR GLOBAL (Principal + Reajuste)
    resultado['TOTAL_GLOBAL_ACUM'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Estilização das Unidades Construtivas
    def style_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #0e1117'] * len(row)
        return [''] * len(row)

    st.subheader("✅ Histórico Consolidado (Conferência de Reajuste)")
    st.dataframe(resultado.style.apply(style_rows, axis=1), use_container_width=True)
    
    # Download
    output = io.BytesIO()
    resultado.to_excel(output, index=False)
    st.download_button("📥 Baixar Planilha de Histórico", output.getvalue(), "historico_consolidado_reajuste.xlsx")
