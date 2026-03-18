import streamlit as st
import pandas as pd
import io
import re
import xlsxwriter 

st.set_page_config(page_title="Consolidador GOINFRA Estruturado", layout="wide")
st.title("📑 Histórico Estruturado e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def formatar_br(valor):
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def analisar_planilha_dinamica(file):
    """Busca dinâmica de Medição e Cabeçalhos conforme solicitado."""
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_busca = pd.read_excel(file, nrows=60, header=None, engine=engine)
        
        num_bm = 999
        linha_cabecalho = None
        mapa = {}

        for i, linha in df_busca.iterrows():
            linha_str = [str(c).strip().upper() for c in linha]
            
            # Busca do nº da medição (X - Xº Medição)
            if any("MEDIÇÃO" in s for s in linha_str):
                for celula in linha_str:
                    if "MEDIÇÃO" in celula:
                        match = re.search(r'(\d+)', celula)
                        if match: num_bm = int(match.group(1))

            # Busca da linha 'CÓDIGO' e mapeamento de colunas
            if "CÓDIGO" in linha_str:
                linha_cabecalho = i
                for idx, col_nome in enumerate(linha_str):
                    if "CÓDIGO" == col_nome: mapa['COD'] = idx
                    elif "SERVIÇO" in col_nome: mapa['SERV'] = idx
                    elif "UNID" in col_nome: mapa['UNID'] = idx
                    elif "UNITÁRIO" in col_nome: mapa['VUNIT'] = idx
                    elif "CONTRATADA" in col_nome: mapa['QCONT'] = idx
                    elif "REAJUSTAMENTO" in col_nome: mapa['REAJ'] = idx
                    elif "DA MEDIÇÃO" in col_nome:
                        if 'QMED' not in mapa: mapa['QMED'] = idx
                        else: mapa['VMED'] = idx
                break
        return num_bm, linha_cabecalho, mapa
    except: return 999, None, {}

if uploaded_files:
    # 1. ORDENAÇÃO DINÂMICA
    arquivos_info = []
    for f in uploaded_files:
        n, lin, m = analisar_planilha_dinamica(f)
        if lin is not None:
            arquivos_info.append({'file': f, 'n': n, 'linha_ini': lin, 'mapa': m})
    
    processados = sorted(arquivos_info, key=lambda x: x['n'])

    esqueleto_mestre = []
    dados_por_item = {}
    historico_valores = {}

    # 2. CONSTRUÇÃO DO ESQUELETO
    for info in processados:
        label = f"BM_{info['n']:02d}"
        mapa = info['mapa']
        df = pd.read_excel(info['file'], skiprows=info['linha_ini'] + 1, header=None)
        
        # Corte no TOTAL MÃO-DE-OBRA
        idx_cod = mapa.get('COD', 0)
        corte = df[df.iloc[:, idx_cod].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df = df.iloc[:corte[0]]

        uc_atual = "INÍCIO"
        contagem_oc = {}

        for _, row in df.iterrows():
            cod = str(row[mapa.get('COD', 0)]).strip() if not pd.isna(row[mapa.get('COD')]) else ""
            serv = str(row[mapa.get('SERV', 1)]).strip() if not pd.isna(row[mapa.get('SERV')]) else ""
            unid = str(row[mapa.get('UNID', 2)]).strip() if 'UNID' in mapa and not pd.isna(row[mapa['UNID']]) else ""
            
            if (unid == "" or unid == "nan" or unid == "0") and serv != "":
                uc_atual = serv
            
            chave_base = f"{uc_atual}|{cod}|{serv}"
            contagem_oc[chave_base] = contagem_oc.get(chave_base, 0) + 1
            chave_final = f"{chave_base}|{contagem_oc[chave_base]}"

            if chave_final not in dados_por_item:
                dados_por_item[chave_final] = {
                    'COD': cod, 'SERVICO': serv, 'UNID': unid, 
                    'VAL_UNIT': row[mapa.get('VUNIT', 0)] if 'VUNIT' in mapa else 0,
                    'QTD_CONTR': row[mapa.get('QCONT', 0)] if 'QCONT' in mapa else 0
                }
                esqueleto_mestre.append(chave_final)
            
            if chave_final not in historico_valores: historico_valores[chave_final] = {}
            historico_valores[chave_final][f'QTD_{label}'] = pd.to_numeric(row[mapa.get('QMED')], errors='coerce') if 'QMED' in mapa else 0
            historico_valores[chave_final][f'VAL_{label}'] = pd.to_numeric(row[mapa.get('VMED')], errors='coerce') if 'VMED' in mapa else 0
            historico_valores[chave_final][f'REAJ_{label}'] = pd.to_numeric(row[mapa.get('REAJ')], errors='coerce') if 'REAJ' in mapa else 0

    # 3. MONTAGEM DO DATAFRAME FINAL
    linhas_finais = []
    for chave in esqueleto_mestre:
        row_data = dados_por_item[chave].copy()
        for info in processados:
            l = f"BM_{info['n']:02d}"
            row_data[f'QTD_{l}'] = historico_valores[chave].get(f'QTD_{l}', 0)
            row_data[f'VAL_{l}'] = historico_valores[chave].get(f'VAL_{l}', 0)
            row_data[f'REAJ_{l}'] = historico_valores[chave].get(f'REAJ_{l}', 0)
        linhas_finais.append(row_data)

    resultado = pd.DataFrame(linhas_finais).fillna(0)

    # 4. TOTAIS
    cols_qtd = [c for c in resultado.columns if 'QTD_BM' in c]
    cols_val = [c for c in resultado.columns if 'VAL_BM' in c]
    cols_reaj = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['SOMA_QTD'] = resultado[cols_qtd].sum(axis=1)
    resultado['SOMA_VALOR'] = resultado[cols_val].sum(axis=1)
    resultado['SOMA_REAJUSTE'] = resultado[cols_reaj].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['SOMA_VALOR'] + resultado['SOMA_REAJUSTE']

    # 5. EXIBIÇÃO E ESTILO (RESTITUÍDO)
    servicos_reais = resultado[~resultado['UNID'].astype(str).str.strip().isin(['', '0', '0.0', 'nan'])].copy()
    soma_v = servicos_reais['SOMA_VALOR'].sum()
    soma_r = servicos_reais['SOMA_REAJUSTE'].sum()
    
    linha_total = pd.DataFrame([{'SERVICO': '>>> TOTAL GERAL DA OBRA', 'SOMA_VALOR': soma_v, 'SOMA_REAJUSTE': soma_r, 'TOTAL_GERAL': soma_v+soma_r}])
    df_exibicao = pd.concat([resultado, linha_total], ignore_index=True).fillna(0)

    st.subheader("✅ Histórico Consolidado e Estruturado")

    def estilo_goinfra(row):
        if ">>> TOTAL" in str(row['SERVICO']):
            return ['background-color: #002b36; color: white; font-weight: bold'] * len(row)
        unid_str = str(row['UNID']).strip()
        if unid_str in ["", "0", "0.0", "nan"]:
            return ['background-color: #f0f2f6; color: #1f77b4; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(df_exibicao.style.apply(estilo_goinfra, axis=1).format({c: formatar_br for c in df_exibicao.select_dtypes('number').columns}), use_container_width=True)

    # --- ABA: CURVA ABC (RESTITUÍDO LÓGICA ORIGINAL) ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC (Baseada em Preços Iniciais - PI)")

    st.info("""
    **Legenda e Metodologia do Relatório:**
    * **PI (Preço Inicial):** Valor acumulado das medições calculado com os preços unitários do contrato original.
    * **Reajustamento:** Valor da correção monetária acumulada sobre o PI.
    * **Curva ABC:** O ranking e a classificação são calculados exclusivamente sobre o **PI**.
    * **Critério de Corte (Inclusivo):** Pertencem à **Classe A** todos os itens até o primeiro serviço que atinge ou ultrapassa o acumulado de 80%.
    """)

    abc = servicos_reais[servicos_reais['SOMA_VALOR'] > 0.01].copy()
    if not abc.empty:
        abc = abc.sort_values(by='SOMA_VALOR', ascending=False)
        total_pi_abc = abc['SOMA_VALOR'].sum()
        total_reaj_abc = abc['SOMA_REAJUSTE'].sum()
        abc['%_SIMPLES'] = (abc['SOMA_VALOR'] / total_pi_abc) * 100
        abc['%_ACC'] = abc['%_SIMPLES'].cumsum()
        
        def classificar_inclusivo(row):
            idx = abc.index.get_loc(row.name)
            if idx == 0: return 'A'
            acc_anterior = abc.iloc[idx - 1]['%_ACC']
            if acc_anterior < 80.0: return 'A'
            elif acc_anterior < 95.0: return 'B'
            return 'C'

        abc['CLASSE'] = abc.apply(classificar_inclusivo, axis=1)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Acumulado (PI)", f"R$ {formatar_br(total_pi_abc)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(total_reaj_abc)}")
        m3.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")
        m4.metric("Itens Classe B", f"{len(abc[abc['CLASSE'] == 'B'])}")

        def color_classe(val):
            color = '#d9534f' if val == 'A' else ('#f0ad4e' if val == 'B' else '#5cb85c')
            return f'color: {color}; font-weight: bold'

        abc_view = abc[['COD', 'SERVICO', 'UNID', 'SOMA_VALOR', '%_ACC', 'CLASSE']].rename(columns={'SOMA_VALOR': 'VALOR ACUMULADO (PI)'})
        st.dataframe(abc_view.style.format({'VALOR ACUMULADO (PI)': formatar_br, '%_ACC': "{:.2f}%"}).applymap(color_classe, subset=['CLASSE']), use_container_width=True)

    # --- 6. EXPORTAÇÃO (RESTITUÍDO FORMATAÇÃO ORIGINAL) ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_hist_export = df_exibicao.copy()
        novos_nomes = {}
        for col in df_hist_export.columns:
            if col.startswith('QTD_BM_'): novos_nomes[col] = f'Quantidade BM {col.split("_")[-1]}'
            elif col.startswith('VAL_BM_'): novos_nomes[col] = f'Valor BM {col.split("_")[-1]}'
            elif col.startswith('REAJ_BM_'): novos_nomes[col] = f'Valor Reajuste BM {col.split("_")[-1]}'
        
        df_hist_export.rename(columns=novos_nomes, inplace=True)
        df_hist_export.to_excel(writer, sheet_name='Historico_Consolidado', index=False)
        
        if not abc.empty:
            abc_export = abc[['COD', 'SERVICO', 'UNID', 'SOMA_VALOR', '%_ACC', 'CLASSE']].rename(columns={'SOMA_VALOR': 'VALOR ACUMULADO (PI)'})
            abc_export.to_excel(writer, sheet_name='Curva_ABC', index=False)

        workbook = writer.book
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#002b36', 'font_color': 'white', 'border': 1, 'align': 'center'})
        fmt_num = workbook.add_format({'num_format': '#,##0.00'})
        fmt_perc = workbook.add_format({'num_format': '0.00"%"'})
        fmt_uc = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
        fmt_classe_a = workbook.add_format({'bold': True})

        ws1 = writer.sheets['Historico_Consolidado']
        for col_num, value in enumerate(df_hist_export.columns):
            ws1.write(0, col_num, value, fmt_header)
            ws1.set_column(col_num, col_num, 60 if value == 'SERVICO' else 18, fmt_num)

        for row_num in range(len(df_hist_export)):
            unid_val = str(df_hist_export.iloc[row_num]['UNID']).strip()
            if unid_val in ["", "0", "0.0", "nan"]:
                ws1.set_row(row_num + 1, None, fmt_uc)

        if not abc.empty:
            ws2 = writer.sheets['Curva_ABC']
            for col_num, value in enumerate(abc_export.columns):
                ws2.write(0, col_num, value, fmt_header)
                ws2.set_column(col_num, col_num, 60 if value == 'SERVICO' else 18, fmt_perc if '%_ACC' in value else fmt_num)
            for row_num in range(len(abc_export)):
                if abc_export.iloc[row_num]['CLASSE'] == 'A': ws2.set_row(row_num + 1, None, fmt_classe_a)

    st.sidebar.download_button("📥 Baixar Relatório Profissional", output.getvalue(), "relatorio_goinfra_final.xlsx")
