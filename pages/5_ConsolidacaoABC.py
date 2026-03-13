import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Consolidador GOINFRA Final", layout="wide")
st.title("📑 Consolidador de Histórico (Correção de Colunas)")

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
        if v == 0: return "0,00"
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

if uploaded_files:
    processados = []
    for file in uploaded_files:
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            # Lemos apenas o cabeçalho para pegar o número da BM
            df_cab = pd.read_excel(file, nrows=15, usecols="J", header=None, engine=engine)
            texto_bm = str(df_cab.iloc[11, 0])
            num = re.findall(r'(\d+)', texto_bm)
            n = int(num[0]) if num else 999
            processados.append({'file': file, 'ordem': n, 'label': f"BM_{n:02d}"})
        except: pass
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. ESTRUTURA MESTRE (Baseada no ÚLTIMO arquivo carregado)
    try:
        u_item = processados[-1]
        eng_u = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        # Lemos sem nomes de colunas primeiro para evitar o erro de "None"
        df_mestre_raw = pd.read_excel(u_item['file'], skiprows=25, header=None, engine=eng_u)
        
        # Filtro de corte: para quando achar "TOTAL" na primeira ou segunda coluna
        corte = df_mestre_raw[df_mestre_raw.iloc[:, 0].astype(str).str.contains("TOTAL", na=False) | 
                              df_mestre_raw.iloc[:, 1].astype(str).str.contains("TOTAL", na=False)].index
        if not corte.empty: df_mestre_raw = df_mestre_raw.iloc[:corte[0]]

        # Atribuímos nomes fixos baseados na posição
        resultado = pd.DataFrame()
        resultado['COD'] = df_mestre_raw.iloc[:, 0].astype(str)
        resultado['SERVICO'] = df_mestre_raw.iloc[:, 1].astype(str)
        resultado['UNID'] = df_mestre_raw.iloc[:, 2].astype(str)
        resultado['PRECO_UNIT'] = pd.to_numeric(df_mestre_raw.iloc[:, 3], errors='coerce').fillna(0)
        resultado['QTD_ORC'] = pd.to_numeric(df_mestre_raw.iloc[:, 4], errors='coerce').fillna(0)
        
        # Chave de busca para o dicionário
        resultado['KEY'] = resultado['SERVICO'].apply(normalizar)
        resultado['ORDEM'] = range(len(resultado))
    except Exception as e:
        st.error(f"Erro na estrutura: {e}")
        st.stop()

    # 2. BUSCA DINÂMICA EM CADA ARQUIVO
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_atual = pd.read_excel(item['file'], skiprows=25, header=None, engine=eng)
            
            # Criamos a chave de busca na medição atual (Coluna B / Índice 1)
            df_atual['KEY'] = df_atual.iloc[:, 1].apply(normalizar)
            
            # Localizamos as colunas de Quantidade e Valor (Geralmente F e G ou H e I)
            # Na GOINFRA, costumam ser as colunas 5 e 6 (índices 0-based) ou similares
            # Para garantir, vamos procurar onde estão os valores numéricos após a coluna 4
            dict_qtd = pd.Series(df_atual.iloc[:, 5].values, index=df_atual['KEY']).to_dict()
            dict_val = pd.Series(df_atual.iloc[:, 6].values, index=df_atual['KEY']).to_dict()
            
            # Reajuste costuma estar na coluna 8 ou 9
            dict_reaj = {}
            if df_atual.shape[1] > 8:
                dict_reaj = pd.Series(df_atual.iloc[:, 8].values, index=df_atual['KEY']).to_dict()

            resultado[f'QTD_{item["label"]}'] = resultado['KEY'].map(dict_qtd).fillna(0)
            resultado[f'VALOR_{item["label"]}'] = resultado['KEY'].map(dict_val).fillna(0)
            resultado[f'REAJ_{item["label"]}'] = resultado['KEY'].map(dict_reaj).fillna(0)
        except:
            st.warning(f"Não foi possível extrair dados de {item['label']}")

    # 3. CONSOLIDAÇÃO FINAL
    # Convertemos colunas para numérico antes de somar
    cols_v = [c for c in resultado.columns if 'VALOR_BM' in c]
    cols_r = [c for c in resultado.columns if 'REAJ_BM' in c]
    
    resultado['VALOR_ACUMULADO'] = resultado[cols_v].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[cols_r].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- EXIBIÇÃO ---
    st.subheader("✅ Histórico Consolidado (Busca por Nome)")
    df_view = resultado.drop(columns=['KEY', 'ORDEM'])
    
    # Formatação de Estilo
    def style_fn(row):
        return ['background-color: #f8f9fa; font-weight: bold' if row['PRECO_UNIT'] == 0 else '' for _ in row]

    st.dataframe(
        df_view.style.apply(style_fn, axis=1)
        .format({c: formatar_br for c in df_view.select_dtypes(include=['float64', 'int64']).columns}),
        use_container_width=True
    )

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    if not abc.empty:
        st.subheader("📈 Curva ABC")
        abc = abc.sort_values('TOTAL_GERAL', ascending=False)
        t_global = abc['TOTAL_GERAL'].sum()
        abc['%_ACUM'] = ((abc['TOTAL_GERAL'] / t_global) * 100).cumsum()
        abc['CLASSE'] = abc['%_ACUM'].apply(lambda p: 'A' if p <= 80.1 else ('B' if p <= 95.1 else 'C'))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Serviços (PI)", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        c2.metric("Total Reajuste", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        c3.metric("Total Geral", f"R$ {formatar_br(t_global)}")
        
        st.dataframe(
            abc[['COD', 'SERVICO', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', 'CLASSE']]
            .style.format({c: formatar_br for c in ['VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL']}),
            use_container_width=True
        )

    # Botão de Download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_view.to_excel(writer, index=False)
    st.sidebar.download_button("📥 Baixar Excel", output.getvalue(), "relatorio_final.xlsx")
