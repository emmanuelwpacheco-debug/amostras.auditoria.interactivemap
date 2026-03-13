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

def normalizar_texto(txt):
    if pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    return txt

def formatar_br(valor):
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if uploaded_files:
    processados = []
    for file in uploaded_files:
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            df_cab = pd.read_excel(file, nrows=15, usecols="J", header=None, engine=engine)
            num = re.findall(r'(\d+)', str(df_cab.iloc[11, 0]))
            ordem = int(num[0]) if num else 999
            processados.append({'file': file, 'ordem': ordem, 'label': f"BM_{ordem:02d}"})
        except: pass
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. Esqueleto Base
    try:
        u_item = processados[-1]
        eng_m = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        # Lemos SEM cabeçalho para garantir que pegamos as colunas pela posição correta
        df_m = pd.read_excel(u_item['file'], skiprows=25, header=None, engine=eng_m)
        
        # Corte no total
        corte = df_m[df_m.iloc[:, 1].astype(str).str.contains("TOTAL|MÃO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df_m = df_m.iloc[:corte[0]]

        resultado = pd.DataFrame()
        resultado['COD'] = df_m.iloc[:, 0].astype(str)
        resultado['SERVICO'] = df_m.iloc[:, 1].astype(str)
        resultado['UNID'] = df_m.iloc[:, 2].astype(str)
        resultado['PRECO_UNIT'] = pd.to_numeric(df_m.iloc[:, 3], errors='coerce').fillna(0)
        resultado['QTD_ORC'] = pd.to_numeric(df_m.iloc[:, 4], errors='coerce').fillna(0)
        
        # Chave de busca robusta (Código + Serviço)
        resultado['KEY'] = (resultado['COD'].apply(normalizar_texto) + 
                           resultado['SERVICO'].apply(normalizar_texto))
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
    except Exception as e:
        st.error(f"Erro na estrutura mestre: {e}")
        st.stop()

    # 2. Busca Dinâmica de Valores Parciais
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, header=None, engine=eng)
            
            # Criamos a chave na medição atual
            df_bm['KEY'] = (df_bm.iloc[:, 0].astype(str).apply(normalizar_texto) + 
                            df_bm.iloc[:, 1].astype(str).apply(normalizar_texto))
            
            # --- POSIÇÕES CRÍTICAS (GOINFRA) ---
            # Coluna 5: Qtd Medição | Coluna 6: Valor Medição | Coluna 8 ou 9: Reajuste
            dict_qtd = pd.Series(df_bm.iloc[:, 5].values, index=df_bm['KEY']).to_dict()
            dict_val = pd.Series(df_bm.iloc[:, 6].values, index=df_bm['KEY']).to_dict()
            
            dict_reaj = {}
            if df_bm.shape[1] > 8:
                dict_reaj = pd.Series(df_bm.iloc[:, 8].values, index=df_bm['KEY']).to_dict()

            label = item['label']
            resultado[f'QTD_{label}'] = resultado['KEY'].map(dict_qtd).apply(pd.to_numeric, errors='coerce').fillna(0)
            resultado[f'VALOR_{label}'] = resultado['KEY'].map(dict_val).apply(pd.to_numeric, errors='coerce').fillna(0)
            resultado[f'REAJ_{label}'] = resultado['KEY'].map(dict_reaj).apply(pd.to_numeric, errors='coerce').fillna(0)
            
        except Exception as e:
            st.warning(f"Erro ao processar {item['label']}: {e}")

    # 3. Consolidação e Curva ABC
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- EXIBIÇÃO HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    df_final = resultado.drop(columns=['KEY', 'ORDEM_ORIGINAL'])
    
    st.dataframe(
        df_final.style.apply(lambda r: ['background-color: #f0f2f6; font-weight: bold'] * len(r) if r['PRECO_UNIT'] == 0 else [''] * len(r), axis=1)
        .format({c: formatar_br for c in df_final.select_dtypes(include=['float64']).columns}),
        use_container_width=True
    )

    # --- ABA: CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01].sort_values(by='TOTAL_GERAL', ascending=False)
    
    if not abc.empty:
        st.subheader("📈 Curva ABC")
        total_g = abc['TOTAL_GERAL'].sum()
        abc['%_ACUM'] = ((abc['TOTAL_GERAL'] / total_g) * 100).cumsum()
        abc['CLASSE'] = abc['%_ACUM'].apply(lambda p: 'A' if p <= 80.1 else ('B' if p <= 95.1 else 'C'))
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        m3.metric("Total Global", f"R$ {formatar_br(total_g)}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', 'CLASSE']]
            .style.format({c: formatar_br for c in ['VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL']}),
            use_container_width=True
        )

    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False)
    st.sidebar.download_button("📥 Baixar Excel", output.getvalue(), "relatorio_consolidado.xlsx")
