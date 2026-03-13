import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Histórico Cronológico GOINFRA", layout="wide")
st.title("📑 Consolidador Inteligente (Ordenação por Cabeçalho)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (não importa a ordem de upload)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def extrair_info_medicao(file):
    """Lê a linha 12 para identificar o número ou período da medição para ordenação"""
    try:
        # Lê apenas as primeiras linhas para performance
        df_header = pd.read_excel(file, nrows=15, header=None)
        # Linha 12 no Excel é índice 11 no Python
        info_linha_12 = str(df_header.iloc[11].dropna().iloc[0])
        
        # Tenta extrair o número da medição (ex: "7ª", "12", "01")
        numeros = re.findall(r'(\d+)', info_linha_12)
        ordem = int(numeros[0]) if numeros else 999
        return ordem, info_linha_12
    except:
        return 999, "Medição Não Identificada"

if uploaded_files:
    lista_processada = []
    
    # 1. PRIMEIRA PASSAGEM: Identificar Ordem e Metadados
    for file in uploaded_files:
        ordem, label = extrair_info_medicao(file)
        lista_processada.append({
            'file': file,
            'ordem': ordem,
            'label': f"BM_{ordem:02d}"
        })
    
    # Ordena a lista de arquivos pela cronologia detectada
    lista_processada = sorted(lista_processada, key=lambda x: x['ordem'])
    
    # 2. SEGUNDA PASSAGEM: Ler dados usando a última medição como esqueleto
    dados_bms = {}
    
    # Usamos o último arquivo da lista (mais recente) para definir a estrutura
    arquivo_mestre = lista_processada[-1]['file']
    try:
        df_mestre_bruto = pd.read_excel(arquivo_mestre, skiprows=25)
        df_mestre_bruto.columns = [str(c).strip().upper() for c in df_mestre_bruto.columns]
        df_mestre_bruto = df_mestre_bruto.loc[:, ~df_mestre_bruto.columns.str.contains('UNNAMED|NAN', case=False)]
        
        c_cod = df_mestre_bruto.columns[0]
        c_serv = df_mestre_bruto.columns[1]
        c_unid = next((c for c in df_mestre_bruto.columns if 'UNID' in c), df_mestre_bruto.columns[2])
        c_precu = next((c for c in df_mestre_bruto.columns if 'UNIT' in c), df_mestre_bruto.columns[3])
        c_qtd_orc = next((c for c in df_mestre_bruto.columns if 'CONTRATADA' in c or 'QTD. ORC' in c), df_mestre_bruto.columns[4])
        
        resultado = df_mestre_bruto[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
    except Exception as e:
        st.error(f"Erro ao processar estrutura mestre: {e}")
        st.stop()

    # 3. ENCAIXAR DADOS DE CADA BM NA ORDEM CRONOLÓGICA
    for item in lista_processada:
        try:
            df_bm = pd.read_excel(item['file'], skiprows=25)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            label = item['label']
            
            # Localizar colunas de interesse
            cols_medicao = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj_nome = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            c_k0_nome = next((c for c in df_bm.columns if 'K0' in c or 'FATOR' in c or '(K)' in c), None)

            med_temp = pd.DataFrame(index=df_bm.index)
            
            # Captura Qtd e Valor (as duas colunas "Da Medição")
            if len(cols_medicao) >= 2:
                med_temp[f'QTD_{label}'] = pd.to_numeric(df_bm[cols_medicao[0]], errors='coerce').fillna(0)
                med_temp[f'VALOR_{label}'] = pd.to_numeric(df_bm[cols_medicao[1]], errors='coerce').fillna(0)
            
            # Reajuste e K0
            if c_reaj_nome:
                med_temp[f'REAJ_{label}'] = pd.to_numeric(df_bm[c_reaj_nome], errors='coerce').fillna(0)
            if c_k0_nome:
                med_temp[f'K0_{label}'] = df_bm[c_k0_nome].fillna(1.0)
            
            # Unir ao resultado garantindo que o índice da linha seja respeitado
            resultado = resultado.join(med_temp)
            
        except Exception as e:
            st.warning(f"Erro no arquivo {item['file'].name}: {e}")

    # 4. CONSOLIDAÇÃO FINAL
    resultado = resultado.fillna(0)
    
    # Somas Acumuladas
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Estilização
    def style_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.subheader(f"✅ Histórico Ordenado ({len(lista_processada)} Medições Detectadas)")
    st.info(f"Esqueleto base obtido da medição mais recente: {lista_processada[-1]['file'].name}")
    
    st.dataframe(resultado.style.apply(style_rows, axis=1), use_container_width=True)
    
    # Download
    output = io.BytesIO()
    resultado.to_excel(output, index=False)
    st.download_button("📥 Baixar Histórico Cronológico", output.getvalue(), "historico_cronologico_goinfra.xlsx")
