import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

# --- FUNÇÕES DE APOIO (MANTIDAS) ---
def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_cabecalho = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()
        numeros = re.findall(r'(\d+)', texto_j12)
        if numeros:
            num = int(numeros[0])
            return num, f"BM_{num:02d}"
        return 999, "BM_Erro"
    except:
        return 999, "BM_Erro"

def formatar_br(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalizar_chave(txt):
    if pd.isna(txt): return ""
    return str(txt).strip().upper()

# --- PROCESSAMENTO ---
if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. Esqueleto Base (Última Medição)
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        
        # Corte dinâmico
        linha_corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_corte.empty:
            df_m = df_m.iloc[:linha_corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        
        # Identificação robusta das colunas do mestre
        resultado = df_m.iloc[:, [0, 1, 2, 3, 4]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        resultado['CHAVE_JOIN'] = resultado['COD'].apply(normalizar_chave) + resultado['SERVICO'].apply(normalizar_chave)
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        
    except Exception as e:
        st.error(f"Erro na estrutura mestre: {e}")
        st.stop()

    # 2. Integração de Dados (CORREÇÃO DOS VALORES INTERMEDIÁRIOS)
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            cols_originais = [str(c).strip().upper() for c in df_bm.columns]
            df_bm.columns = cols_originais
            label = item['label']
            
            # --- LÓGICA DE DETECÇÃO POR ÍNDICE ---
            # Localiza onde começa o bloco "DA MEDIÇÃO"
            idx_medicao = -1
            for i, col in enumerate(cols_originais):
                if 'DA MEDIÇÃO' in col:
                    idx_medicao = i
                    break
            
            # Localiza o Reajuste
            idx_reaj = -1
            for i, col in enumerate(cols_originais):
                if 'REAJUSTE' in col or 'REAJUSTAMENTO' in col:
                    idx_reaj = i
                    break

            # Criar DataFrame temporário para a medição
            df_bm['CHAVE_JOIN'] = df_bm.iloc[:, 0].apply(normalizar_chave) + df_bm.iloc[:, 1].apply(normalizar_chave)
            
            med_cols = pd.DataFrame()
            med_cols['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            
            if idx_medicao != -1:
                # Padrão GOINFRA: Quantidade é a coluna achada, Valor é a próxima (mesmo que seja Unnamed)
                med_cols[f'QTD_{label}'] = pd.to_numeric(df_bm.iloc[:, idx_medicao], errors='coerce').fillna(0)
                med_cols[f'VALOR_{label}'] = pd.to_numeric(df_bm.iloc[:, idx_medicao + 1], errors='coerce').fillna(0)
            
            if idx_reaj != -1:
                med_cols[f'REAJ_{label}'] = pd.to_numeric(df_bm.iloc[:, idx_reaj], errors='coerce').fillna(0)
            
            med_cols = med_cols.drop_duplicates(subset=['CHAVE_JOIN'])
            resultado = pd.merge(resultado, med_cols, on='CHAVE_JOIN', how='left')
            
        except Exception as e:
            st.warning(f"Erro no arquivo {item['file'].name}: {e}")

    # 3. Consolidação Final (MANTIDA)
    resultado = resultado.sort_values('ORDEM_ORIGINAL').fillna(0)
    
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- TELA E CURVA ABC (MANTIDAS) ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    def format_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    colunas_finais = resultado.drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL'])
    st.dataframe(
        colunas_finais.style.apply(format_rows, axis=1)
        .format({c: formatar_br for c in colunas_finais.select_dtypes(include=['float64', 'int64']).columns}), 
        use_container_width=True
    )

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01].sort_values(by='TOTAL_GERAL', ascending=False)
    
    if not abc.empty:
        st.subheader("📈 Análise de Curva ABC")
        total_global = abc['TOTAL_GERAL'].sum()
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / total_global) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(lambda p: 'A' if p <= 80.01 else ('B' if p <= 95.01 else 'C'))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        m3.metric("Total Global", f"R$ {formatar_br(total_global)}")
        m4.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', '%_ACUMULADO', 'CLASSE']]
            .style.format({
                'VALOR_ACUMULADO': formatar_br, 'REAJUSTE_ACUMULADO': formatar_br,
                'TOTAL_GERAL': formatar_br, '%_ACUMULADO': "{:.2f}%"
            }).applymap(lambda v: f'color: {"#d9534f" if v=="A" else ("#f0ad4e" if v=="B" else "#5cb85c")}; font-weight: bold', subset=['CLASSE']),
            use_container_width=True
        )

    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        colunas_finais.to_excel(writer, sheet_name='Historico', index=False)
    st.sidebar.download_button("📥 Baixar Relatório Final", output.getvalue(), "consolidado_goinfra.xlsx")
