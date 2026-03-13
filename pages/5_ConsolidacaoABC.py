import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador Cronológico GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico Fidedigno")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def extrair_id_medicao(file):
    """Lê especificamente a célula J12 para identificar a medição (ex: '1 - 1ª Medição')"""
    try:
        # Tenta ler com xlrd para arquivos .xls antigos
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        # Lê apenas a área do cabeçalho (até linha 12, coluna J)
        df_cabecalho = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        
        # Célula J12 é índice [11, 0] no dataframe de uma única coluna
        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()
        
        # Extrai o primeiro número (ex: de '1 - 1ª Medição' extrai '1')
        numeros = re.findall(r'(\d+)', texto_j12)
        if numeros:
            num = int(numeros[0])
            return num, f"BM_{num:02d}"
        
        return 999, f"BM_{file.name[:10]}"
    except Exception as e:
        return 999, f"BM_Erro"

if uploaded_files:
    processados = []
    
    # 1. Identificação Cronológica
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    # Ordena os arquivos pela medição (1, 2, 3...)
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 2. Esqueleto Base (Usa a medição mais recente para ter o orçamento atualizado)
    try:
        ultimo_item = processados[-1]
        engine_mestre = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_mestre = pd.read_excel(ultimo_item['file'], skiprows=25, engine=engine_mestre)
        df_mestre.columns = [str(c).strip().upper() for c in df_mestre.columns]
        df_mestre = df_mestre.loc[:, ~df_mestre.columns.str.contains('UNNAMED|NAN', case=False)]
        
        # Mapeamento de colunas fixas
        c_cod = df_mestre.columns[0]
        c_serv = df_mestre.columns[1]
        c_unid = next((c for c in df_mestre.columns if 'UNID' in c), df_mestre.columns[2])
        c_precu = next((c for c in df_mestre.columns if 'UNIT' in c), df_mestre.columns[3])
        c_qtd_orc = next((c for c in df_mestre.columns if 'CONTRATADA' in c or 'QTD. ORC' in c), df_mestre.columns[4])
        
        resultado = df_mestre[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        resultado['ID_LINHA'] = resultado.index
    except Exception as e:
        st.error(f"Erro ao processar estrutura mestre: {e}")
        st.stop()

    # 3. Integração de Dados
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            label = item['label']
            
            # Localizar colunas de medição
            cols_med = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            c_k0 = next((c for c in df_bm.columns if 'K0' in c or 'FATOR' in c), None)

            med_cols = pd.DataFrame(index=df_bm.index)
            if len(cols_med) >= 2:
                med_cols[f'QTD_{label}'] = pd.to_numeric(df_bm[cols_med[0]], errors='coerce').fillna(0)
                med_cols[f'VALOR_{label}'] = pd.to_numeric(df_bm[cols_med[1]], errors='coerce').fillna(0)
            
            if c_reaj:
                med_cols[f'REAJ_{label}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0)
            if c_k0:
                med_cols[f'K0_{label}'] = df_bm[c_k0].fillna(1.0)
            
            med_cols['ID_LINHA'] = med_cols.index
            resultado = pd.merge(resultado, med_cols, on='ID_LINHA', how='left')
            
        except Exception as e:
            st.error(f"Erro ao ler {item['file'].name}: {e}")

    # 4. Finalização
    resultado = resultado.drop(columns=['ID_LINHA']).fillna(0)
    
    # Somas Acumuladas
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Estilo visual para Unidades Construtivas
    def format_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    st.dataframe(resultado.style.apply(format_rows, axis=1), use_container_width=True)
    
    # Exportação
    output = io.BytesIO()
    resultado.to_excel(output, index=False)
    st.download_button("📥 Baixar Planilha Consolidada", output.getvalue(), "historico_goinfra_final.xlsx")
