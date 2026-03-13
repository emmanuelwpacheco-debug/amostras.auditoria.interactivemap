import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import get_close_matches

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def normalizar_texto(txt):
    if pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    txt = re.sub(r'[^A-Z0-9]', '', txt) # Remove TUDO que não for letra ou número
    return txt

def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_cabecalho = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()
        numeros = re.findall(r'(\d+)', texto_j12)
        return (int(numeros[0]), f"BM_{int(numeros[0]):02d}") if numeros else (999, "BM_Erro")
    except:
        return 999, "BM_Erro"

def formatar_br(valor):
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. Estrutura Mestre (Última Medição)
    try:
        u_item = processados[-1]
        eng_m = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(u_item['file'], skiprows=25, engine=eng_m)
        
        # Corte na linha de totalização
        corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL|MAO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df_m = df_m.iloc[:corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        df_m = df_m.loc[:, ~df_m.columns.str.contains('UNNAMED|NAN', case=False)]
        
        resultado = df_m.iloc[:, [0, 1, 2, 3, 4]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # Chave Ultra Limpa (Apenas letras e números)
        resultado['CHAVE_LIMPA'] = (resultado['COD'].apply(normalizar_texto) + 
                                   resultado['SERVICO'].apply(normalizar_texto))
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
    except Exception as e:
        st.error(f"Erro na leitura mestre: {e}")
        st.stop()

    # 2. Processamento das Medições
    lista_chaves_mestre = resultado['CHAVE_LIMPA'].tolist()

    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            
            # Criar chave de comparação para cada linha da medição
            df_bm['CHAVE_ATUAL'] = (df_bm.iloc[:, 0].apply(normalizar_texto) + 
                                    df_bm.iloc[:, 1].apply(normalizar_texto))
            
            # --- LÓGICA DE FUZZY MATCHING ---
            def encontrar_melhor_chave(chave_atual):
                if chave_atual in lista_chaves_mestre: return chave_atual
                matches = get_close_matches(chave_atual, lista_chaves_mestre, n=1, cutoff=0.8)
                return matches[0] if matches else None

            df_bm['CHAVE_JOIN'] = df_bm['CHAVE_ATUAL'].apply(encontrar_melhor_chave)
            
            # Agrupar valores para as colunas da medição
            cols_med = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            
            med_resumo = pd.DataFrame()
            med_resumo['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            if len(cols_med) >= 2:
                med_resumo[f'QTD_{item["label"]}'] = pd.to_numeric(df_bm[cols_med[0]], errors='coerce').fillna(0)
                med_resumo[f'VALOR_{item["label"]}'] = pd.to_numeric(df_bm[cols_med[1]], errors='coerce').fillna(0)
            if c_reaj:
                med_resumo[f'REAJ_{item["label"]}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0)
            
            # Somar valores caso haja repetição de chaves
            med_resumo = med_resumo.dropna(subset=['CHAVE_JOIN']).groupby('CHAVE_JOIN').sum().reset_index()
            
            resultado = pd.merge(resultado, med_resumo, left_on='CHAVE_LIMPA', right_on='CHAVE_JOIN', how='left').drop(columns=['CHAVE_JOIN'])
            
        except Exception as e:
            st.warning(f"Erro no arquivo {item['file'].name}: {e}")

    # 3. Consolidação e Exibição
    resultado = resultado.sort_values('ORDEM_ORIGINAL').fillna(0)
    
    # Identificar colunas dinâmicas para soma
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- DATAFRAME FINAL ---
    df_show = resultado.drop(columns=['CHAVE_LIMPA', 'ORDEM_ORIGINAL'])
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    st.dataframe(df_show.style.apply(lambda r: ['background-color: #f0f2f6; font-weight: bold'] * len(r) if r['PRECO_UNIT'] == 0 else [''] * len(r), axis=1).format({col: formatar_br for col in df_show.select_dtypes(include=['float64']).columns}), use_container_width=True)

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    if not abc.empty:
        st.subheader("📈 Análise de Curva ABC")
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        total_g = abc['TOTAL_GERAL'].sum()
        abc['%_ACUM'] = ((abc['TOTAL_GERAL'] / total_g) * 100).cumsum()
        abc['CLASSE'] = abc['%_ACUM'].apply(lambda p: 'A' if p <= 80.1 else ('B' if p <= 95.1 else 'C'))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Serviços (PI)", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        c2.metric("Total Reajuste", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        c3.metric("Total Global", f"R$ {formatar_br(total_g)}")
        
        st.dataframe(abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', 'CLASSE']].style.format({col: formatar_br for col in ['VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL']}), use_container_width=True)
