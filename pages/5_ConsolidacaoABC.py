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

def normalizar(txt):
    if pd.isna(txt): return ""
    return unicodedata.normalize('NFKD', str(txt)).encode('ASCII', 'ignore').decode('ASCII').upper().strip()

def formatar_br(valor):
    try:
        v = float(valor)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

if uploaded_files:
    processados = []
    for file in uploaded_files:
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            # Pega o número da medição na célula J12 (índices 11, 9)
            df_cab = pd.read_excel(file, nrows=13, usecols="J", header=None, engine=engine)
            num = re.findall(r'(\d+)', str(df_cab.iloc[11, 0]))
            n = int(num[0]) if num else 999
            processados.append({'file': file, 'ordem': n, 'label': f"BM_{n:02d}"})
        except: pass
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. ESTRUTURA MESTRE (Baseada na última medição carregada)
    try:
        u_item = processados[-1]
        eng_u = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        # Lemos sem cabeçalho (header=None) para evitar nomes como 'Unnamed'
        df_raw = pd.read_excel(u_item['file'], skiprows=25, header=None, engine=eng_u)
        
        # Filtro de segurança: para quando encontrar o resumo final
        corte = df_raw[df_raw.iloc[:, 0].astype(str).str.contains("TOTAL|MÃO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df_raw = df_raw.iloc[:corte[0]]

        # Montamos o esqueleto usando índices de coluna fixos
        resultado = pd.DataFrame()
        resultado['COD'] = df_raw.iloc[:, 0].astype(str).replace('nan', '')
        resultado['SERVICO'] = df_raw.iloc[:, 1].astype(str).replace('nan', '')
        resultado['UNID'] = df_raw.iloc[:, 2].astype(str).replace('nan', '')
        resultado['PRECO_UNIT'] = pd.to_numeric(df_raw.iloc[:, 3], errors='coerce').fillna(0)
        resultado['QTD_ORC'] = pd.to_numeric(df_raw.iloc[:, 4], errors='coerce').fillna(0)
        
        # Chave única para busca (Código + Nome)
        resultado['KEY'] = resultado['COD'].apply(normalizar) + resultado['SERVICO'].apply(normalizar)
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
    except Exception as e:
        st.error(f"Erro ao processar estrutura: {e}")
        st.stop()

    # 2. BUSCA DINÂMICA DE VALORES PARCIAIS
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, header=None, engine=eng)
            
            # Chave na medição atual
            df_bm['KEY'] = df_bm.iloc[:, 0].astype(str).apply(normalizar) + df_bm.iloc[:, 1].astype(str).apply(normalizar)
            
            # Dicionários de busca usando índices fixos das colunas da GOINFRA:
            # Coluna 5 (F): Qtd Medição | Coluna 6 (G): Valor Medição | Coluna 8 (I): Reajuste
            dict_qtd = pd.Series(df_bm.iloc[:, 5].values, index=df_bm['KEY']).to_dict()
            dict_val = pd.Series(df_bm.iloc[:, 6].values, index=df_bm['KEY']).to_dict()
            dict_reaj = {}
            if df_bm.shape[1] > 8:
                dict_reaj = pd.Series(df_bm.iloc[:, 8].values, index=df_bm['KEY']).to_dict()

            label = item['label']
            resultado[f'QTD_{label}'] = resultado['KEY'].map(dict_qtd).apply(pd.to_numeric, errors='coerce').fillna(0)
            resultado[f'VALOR_{label}'] = resultado['KEY'].map(dict_val).apply(pd.to_numeric, errors='coerce').fillna(0)
            resultado[f'REAJ_{label}'] = resultado['KEY'].map(dict_reaj).apply(pd.to_numeric, errors='coerce').fillna(0)
        except:
            st.warning(f"Atenção ao ler {item['label']}: Verifique a estrutura.")

    # 3. CÁLCULOS TOTAIS
    cols_v = [c for c in resultado.columns if 'VALOR_BM' in c]
    cols_r = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['VALOR_ACUMULADO'] = resultado[cols_v].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[cols_r].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- EXIBIÇÃO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    df_final = resultado.drop(columns=['KEY', 'ORDEM_ORIGINAL'])
    
    # Estilo: destaca linhas que são títulos (sem preço unitário)
    st.dataframe(
        df_final.style.apply(lambda r: ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(r) if r['PRECO_UNIT'] == 0 else [''] * len(r), axis=1)
        .format({c: formatar_br for c in df_final.select_dtypes(include=['float64']).columns}),
        use_container_width=True
    )

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01].sort_values(by='TOTAL_GERAL', ascending=False)
    
    if not abc.empty:
        st.subheader("📈 Curva ABC (Somente Serviços)")
        total_global = abc['TOTAL_GERAL'].sum()
        abc['%_ACUM'] = ((abc['TOTAL_GERAL'] / total_global) * 100).cumsum()
        abc['CLASSE'] = abc['%_ACUM'].apply(lambda p: 'A' if p <= 80.1 else ('B' if p <= 95.1 else 'C'))
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Serviços (PI)", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        m2.metric("Reajuste Acum.", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        m3.metric("Total Geral", f"R$ {formatar_br(total_global)}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', 'CLASSE']]
            .style.format({c: formatar_br for c in ['VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL']}),
            use_container_width=True
        )

    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False)
    st.sidebar.download_button("📥 Baixar Relatório", output.getvalue(), "historico_consolidado.xlsx")
