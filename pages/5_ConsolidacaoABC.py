import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Consolidador GOINFRA Final", layout="wide")
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
            df_cab = pd.read_excel(file, nrows=15, usecols="J", header=None, engine=engine)
            num = re.findall(r'(\d+)', str(df_cab.iloc[11, 0]))
            n = int(num[0]) if num else 999
            processados.append({'file': file, 'ordem': n, 'label': f"BM_{n:02d}"})
        except: pass
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. ESTRUTURA MESTRE (Lendo a última BM para montar o esqueleto)
    try:
        u_item = processados[-1]
        eng_u = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        
        # Lemos a aba inteira para detectar onde estão as colunas
        df_full = pd.read_excel(u_item['file'], skiprows=24, engine=eng_u)
        df_full.columns = [str(c).upper().strip() for c in df_full.columns]
        
        # Localização Dinâmica de Colunas Essenciais
        c_cod = df_full.columns[0]
        c_ser = df_full.columns[1]
        c_uni = df_full.columns[2]
        c_pre = next((c for c in df_full.columns if 'UNIT' in c or 'PRECO' in c), df_full.columns[3])
        c_qtd_orc = next((c for c in df_full.columns if 'CONTRATADA' in c or 'ORC' in c), df_full.columns[4])

        # Filtragem de linhas de "Lixo" (Rodapés)
        corte = df_full[df_full.iloc[:, 0].astype(str).str.contains("TOTAL|MÃO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df_full = df_full.iloc[:corte[0]]

        resultado = df_full[[c_cod, c_ser, c_uni, c_pre, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # Chave Única para o Match (DNA do Serviço)
        resultado['KEY'] = resultado['COD'].apply(normalizar) + resultado['SERVICO'].apply(normalizar)
        resultado['PRECO_UNIT'] = pd.to_numeric(resultado['PRECO_UNIT'], errors='coerce').fillna(0)
        
    except Exception as e:
        st.error(f"Erro ao identificar colunas na estrutura mestre: {e}")
        st.stop()

    # 2. CAPTURA DOS DADOS (Busca Dinâmica em cada BM)
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_atual = pd.read_excel(item['file'], skiprows=24, engine=eng)
            df_atual.columns = [str(c).upper().strip() for c in df_atual.columns]
            
            # Detecta as colunas de 'DA MEDIÇÃO' nesta planilha específica
            cols_medicao = [c for c in df_atual.columns if 'DA MEDIÇÃO' in c]
            c_reaj_atual = next((c for c in df_atual.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)

            if len(cols_medicao) >= 2:
                # Cria a chave de busca na BM atual
                df_atual['KEY'] = df_atual.iloc[:, 0].astype(str).apply(normalizar) + df_atual.iloc[:, 1].astype(str).apply(normalizar)
                
                # Mapeamento via dicionário (mais seguro contra mudanças de linha)
                dict_qtd = df_atual.set_index('KEY')[cols_medicao[0]].to_dict()
                dict_val = df_atual.set_index('KEY')[cols_medicao[1]].to_dict()
                dict_reaj = df_atual.set_index('KEY')[c_reaj_atual].to_dict() if c_reaj_atual else {}

                label = item['label']
                resultado[f'QTD_{label}'] = resultado['KEY'].map(dict_qtd).apply(pd.to_numeric, errors='coerce').fillna(0)
                resultado[f'VALOR_{label}'] = resultado['KEY'].map(dict_val).apply(pd.to_numeric, errors='coerce').fillna(0)
                resultado[f'REAJ_{label}'] = resultado['KEY'].map(dict_reaj).apply(pd.to_numeric, errors='coerce').fillna(0)
        except Exception as e:
            st.warning(f"Aviso na {item['label']}: Verifique se os títulos das colunas mudaram.")

    # 3. CÁLCULOS E TELA
    cols_v = [c for c in resultado.columns if 'VALOR_BM' in c]
    cols_r = [c for c in resultado.columns if 'REAJ_BM' in c]
    resultado['VALOR_ACUMULADO'] = resultado[cols_v].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[cols_r].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    # Visualização sem as chaves internas
    df_view = resultado.drop(columns=['KEY'])
    
    st.dataframe(
        df_view.style.apply(lambda r: ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(r) if r['PRECO_UNIT'] == 0 else [''] * len(r), axis=1)
        .format({c: formatar_br for c in df_view.select_dtypes(include=['float64']).columns}),
        use_container_width=True
    )

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01].sort_values(by='TOTAL_GERAL', ascending=False)
    
    if not abc.empty:
        st.subheader("📈 Curva ABC Realizada")
        total_global = abc['TOTAL_GERAL'].sum()
        abc['%_ACUM'] = ((abc['TOTAL_GERAL'] / total_global) * 100).cumsum()
        abc['CLASSE'] = abc['%_ACUM'].apply(lambda p: 'A' if p <= 80.1 else ('B' if p <= 95.1 else 'C'))
        
        m1, m2, m3 = st.columns(3)
        m1.metric("PI Acumulado", f"R$ {formatar_br(abc['VALOR_ACUMULADO'].sum())}")
        m2.metric("Reajuste Acum.", f"R$ {formatar_br(abc['REAJUSTE_ACUMULADO'].sum())}")
        m3.metric("Total Global", f"R$ {formatar_br(total_global)}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', 'CLASSE']]
            .style.format({c: formatar_br for c in ['VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL']})
            .applymap(lambda v: f'color: {"#d9534f" if v=="A" else ("#f0ad4e" if v=="B" else "#5cb85c")}; font-weight: bold', subset=['CLASSE']),
            use_container_width=True
        )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_view.to_excel(writer, index=False)
    st.sidebar.download_button("📥 Baixar Excel", output.getvalue(), "relatorio_goinfra.xlsx")
