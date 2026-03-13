import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador Cronológico GOINFRA", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_cabecalho = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()
        numeros = re.findall(r'(\d+)', texto_j12)
        if numeros:
            num = int(numeros[0])
            return num, f"BM_{num:02d}"
        return 999, f"BM_{file.name[:10]}"
    except:
        return 999, "BM_Erro"

if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. Esqueleto Base
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        df_m = df_m.loc[:, ~df_m.columns.str.contains('UNNAMED|NAN', case=False)]
        
        c_cod = df_m.columns[0]
        c_serv = df_m.columns[1]
        c_unid = next((c for c in df_m.columns if 'UNID' in c), df_m.columns[2])
        c_precu = next((c for c in df_m.columns if 'UNIT' in c), df_m.columns[3])
        c_qtd_orc = next((c for c in df_m.columns if 'CONTRATADA' in c or 'QTD. ORC' in c), df_m.columns[4])
        
        resultado = df_m[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        resultado['ID_LINHA'] = resultado.index
    except Exception as e:
        st.error(f"Erro na estrutura mestre: {e}")
        st.stop()

    # 2. Integração de Dados
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            label = item['label']
            
            cols_med = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            
            med_cols = pd.DataFrame(index=df_bm.index)
            if len(cols_med) >= 2:
                med_cols[f'QTD_{label}'] = pd.to_numeric(df_bm[cols_med[0]], errors='coerce').fillna(0)
                med_cols[f'VALOR_{label}'] = pd.to_numeric(df_bm[cols_med[1]], errors='coerce').fillna(0)
            if c_reaj:
                med_cols[f'REAJ_{label}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0)
            
            med_cols['ID_LINHA'] = med_cols.index
            resultado = pd.merge(resultado, med_cols, on='ID_LINHA', how='left')
        except: pass

    # 3. Consolidação Final
    resultado = resultado.drop(columns=['ID_LINHA']).fillna(0)
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- TELA: HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    def format_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)
    st.dataframe(resultado.style.apply(format_rows, axis=1), use_container_width=True)

    # --- ABA: CURVA ABC ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC (Somente Serviços)")
    
    # Filtro: Remove Unidades Construtivas (Preço Unitário == 0) e itens não medidos
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0]
    
    if not abc.empty:
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        total_acumulado = abc['TOTAL_GERAL'].sum()
        
        # Cálculos de Pareto
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / total_acumulado) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        
        def classificar_abc(porc):
            if porc <= 80: return 'A'
            if porc <= 95: return 'B'
            return 'C'
        
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(classificar_abc)

        # Exibição da Curva ABC
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens Classe A", len(abc[abc['CLASSE'] == 'A']))
        c2.metric("Valor Total Acumulado", f"R$ {total_acumulado:,.2f}")
        c3.metric("Total Reajustes", f"R$ {resultado['REAJUSTE_ACUMULADO'].sum():,.2f}")

        # Estilização da tabela ABC por classe
        def color_classe(val):
            color = '#ff4b4b' if val == 'A' else ('#ffa500' if val == 'B' else '#28a745')
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'TOTAL_GERAL', '%_SIMPLES', '%_ACUMULADO', 'CLASSE']]
            .style.format({'TOTAL_GERAL': '{:,.2f}', '%_SIMPLES': '{:.2f}%', '%_ACUMULADO': '{:.2f}%'})
            .applymap(color_classe, subset=['CLASSE']),
            use_container_width=True
        )
    else:
        st.warning("Não há dados financeiros medidos para gerar a Curva ABC.")

    # Exportação Final
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        resultado.to_excel(writer, sheet_name='Historico_Completo', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório (Excel)", output.getvalue(), "relatorio_consolidado_abc.xlsx")
