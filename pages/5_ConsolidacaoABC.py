import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador GOINFRA Estruturado", layout="wide")
st.title("📑 Histórico Estruturado e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_ref = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto = str(df_ref.iloc[11, 0])
        match = re.search(r'(\d+)', texto)
        return int(match.group(1)) if match else 999
    except: return 999

def formatar_br(valor):
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if uploaded_files:
    # 1. ORDENAÇÃO
    processados = sorted(uploaded_files, key=extrair_id_medicao)
    
    # Dicionário Mestre: Chave Única -> Dados do Item
    # A chave será uma combinação de (Nome da UC + Código + Descrição + Índice de Ocorrência)
    esqueleto_mestre = []
    dados_por_item = {} # Armazena {chave: {colunas_fixas}}
    historico_valores = {} # Armazena {chave: {BM_01: valor, ...}}

    # Mapeamento de Colunas (Índices Reais do Excel - 0-based)
    # A=0, J=9, AD=29, AI=34, AO=40, AU=46, BI=60, CF=83
    IDX_COD = 0; IDX_SERV = 9; IDX_UNID = 29; IDX_VUNIT = 34; IDX_QCONTR = 40
    IDX_QMED = 46; IDX_VMED = 60; IDX_REAJ = 83

    # 2. CONSTRUÇÃO DO ESQUELETO EVOLUTIVO
    for file in processados:
        n_bm = extrair_id_medicao(file)
        label = f"BM_{n_bm:02d}"
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        
        df = pd.read_excel(file, skiprows=25, header=None, engine=engine)
        
        # Corte no "TOTAL MÃO-DE-OBRA"
        corte = df[df.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not corte.empty: df = df.iloc[:corte[0]]

        uc_atual = "INÍCIO"
        contagem_ocorrência = {}

        for _, row in df.iterrows():
            cod = str(row[IDX_COD]).strip() if not pd.isna(row[IDX_COD]) else ""
            serv = str(row[IDX_SERV]).strip() if not pd.isna(row[IDX_SERV]) else ""
            unid = str(row[IDX_UNID]).strip() if not pd.isna(row[IDX_UNID]) else ""
            
            # Identifica Unidade Construtiva (Unid vazia e Serviço presente)
            if (unid == "" or unid == "nan") and serv != "":
                uc_atual = serv
            
            # Gerar Chave Única para rastreabilidade
            chave_base = f"{uc_atual}|{cod}|{serv}"
            contagem_ocorrência[chave_base] = contagem_ocorrência.get(chave_base, 0) + 1
            chave_final = f"{chave_base}|{contagem_ocorrência[chave_base]}"

            # Se o item é novo (Aditivo), insere no esqueleto mestre
            if chave_final not in dados_por_item:
                dados_por_item[chave_final] = {
                    'COD': cod, 'SERVICO': serv, 'UNID': unid, 
                    'VAL_UNIT': row[IDX_VUNIT], 'QTD_CONTR': row[IDX_QCONTR]
                }
                # Mantém a ordem física: se for novo, adicionamos à lista de sequência
                esqueleto_mestre.append(chave_final)
            
            # Armazena os valores desta medição específica
            if chave_final not in historico_valores: historico_valores[chave_final] = {}
            historico_valores[chave_final][f'QTD_{label}'] = pd.to_numeric(row[IDX_QMED], errors='coerce') or 0
            historico_valores[chave_final][f'VAL_{label}'] = pd.to_numeric(row[IDX_VMED], errors='coerce') or 0
            historico_valores[chave_final][f'REAJ_{label}'] = pd.to_numeric(row[IDX_REAJ], errors='coerce') or 0

    # 3. MONTAGEM DO DATAFRAME FINAL
    linhas_finais = []
    for chave in esqueleto_mestre:
        row_data = dados_por_item[chave].copy()
        # Adiciona os valores de cada BM (se não existir na BM, coloca 0)
        for file in processados:
            n = extrair_id_medicao(file)
            l = f"BM_{n:02d}"
            row_data[f'QTD_{l}'] = historico_valores[chave].get(f'QTD_{l}', 0)
            row_data[f'VAL_{l}'] = historico_valores[chave].get(f'VAL_{l}', 0)
            row_data[f'REAJ_{l}'] = historico_valores[chave].get(f'REAJ_{l}', 0)
        linhas_finais.append(row_data)

    resultado = pd.DataFrame(linhas_finais)

    # 4. TOTAIS ACUMULADOS
    cols_qtd = [c for c in resultado.columns if 'QTD_BM' in c]
    cols_val = [c for c in resultado.columns if 'VAL_BM' in c]
    cols_reaj = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['SOMA_QTD'] = resultado[cols_qtd].sum(axis=1)
    resultado['SOMA_VALOR'] = resultado[cols_val].sum(axis=1)
    resultado['SOMA_REAJUSTE'] = resultado[cols_reaj].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['SOMA_VALOR'] + resultado['SOMA_REAJUSTE']

    # 5. LINHA DE TOTAL DA OBRA (SOMENTE ITENS COM UNIDADE)
    servicos_reais = resultado[resultado['UNID'].str.strip() != ""].copy()
    soma_v = servicos_reais['SOMA_VALOR'].sum()
    soma_r = servicos_reais['SOMA_REAJUSTE'].sum()
    
    linha_total = pd.DataFrame([{
        'SERVICO': '>>> TOTAL GERAL DA OBRA',
        'SOMA_VALOR': soma_v, 'SOMA_REAJUSTE': soma_r, 'TOTAL_GERAL': soma_v + soma_r,
        'COD': '', 'UNID': '', 'VAL_UNIT': 0, 'QTD_CONTR': 0
    }])
    
    df_exibicao = pd.concat([resultado, linha_total], ignore_index=True).fillna(0)

    # --- VISUALIZAÇÃO ---
    st.subheader("✅ Histórico Consolidado e Estruturado")

    def estilo_goinfra(row):
        if ">>> TOTAL" in str(row['SERVICO']):
            return ['background-color: #002b36; color: white; font-weight: bold'] * len(row)
        if str(row['UNID']).strip() == "": # É uma Unidade Construtiva
            return ['background-color: #f0f2f6; color: #1f77b4; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_exibicao.style.apply(estilo_goinfra, axis=1).format({c: formatar_br for c in df_exibicao.select_dtypes('number').columns}),
        use_container_width=True
    )

   # --- ABA: CURVA ABC (LÓGICA INCLUSIVA DE FRONTEIRA) ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC (Baseada em PI)")

    # Filtro de serviços com valor medido
    abc = servicos_reais[servicos_reais['SOMA_VALOR'] > 0.01].copy()

    if not abc.empty:
        abc = abc.sort_values(by='SOMA_VALOR', ascending=False)
        
        total_pi_abc = abc['SOMA_VALOR'].sum()
        abc['%_SIMPLES'] = (abc['SOMA_VALOR'] / total_pi_abc) * 100
        abc['%_ACC'] = abc['%_SIMPLES'].cumsum()
        
        # --- NOVA LÓGICA DE CLASSIFICAÇÃO (CRITÉRIO DE CORTE INCLUSIVO) ---
        def classificar_inclusivo(row):
            # Recupera o acumulado da linha anterior para saber se já tínhamos batido a meta
            # Se o acumulado da linha ANTERIOR for menor que 80, esta linha ainda pode ser A
            # Usamos o índice da linha no dataframe ordenado para checar
            idx = abc.index.get_loc(row.name)
            
            if idx == 0: # Primeiro item sempre é A
                return 'A'
            
            acc_anterior = abc.iloc[idx - 1]['%_ACC']
            
            if acc_anterior < 80.0:
                return 'A'
            elif acc_anterior < 95.0:
                return 'B'
            else:
                return 'C'

        abc['CLASSE'] = abc.apply(classificar_inclusivo, axis=1)

        # Resumo Financeiro
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Acumulado (PI)", f"R$ {formatar_br(total_pi_abc)}")
        m2.metric("Itens Classe A", len(abc[abc['CLASSE'] == 'A']))
        m3.metric("Itens Classe B", len(abc[abc['CLASSE'] == 'B']))

        # Estilização
        def color_classe(val):
            color = '#d9534f' if val == 'A' else ('#f0ad4e' if val == 'B' else '#5cb85c')
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'SOMA_VALOR', '%_ACC', 'CLASSE']]
            .rename(columns={'SOMA_VALOR': 'VALOR ACUMULADO (PI)'})
            .style.format({
                'VALOR ACUMULADO (PI)': formatar_br,
                '%_ACC': "{:.2f}%"
            }).applymap(color_classe, subset=['CLASSE']),
            use_container_width=True
        )
        
    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_exibicao.to_excel(writer, index=False, sheet_name='Historico')
    st.sidebar.download_button("📥 Baixar Planilha Master", output.getvalue(), "historico_estruturado.xlsx")
