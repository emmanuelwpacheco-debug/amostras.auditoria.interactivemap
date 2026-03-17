import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Módulo 5 - Consolidador GOINFRA", layout="wide")
st.title("📑 Módulo 5: Histórico de Medições e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as planilhas (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

# --- 1. FUNÇÕES DE SUPORTE ---

def extrair_ordem_j12(file):
    """Lê a célula J12 (Linha 12, Coluna J) para ordenar as medições."""
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        # J12 é linha 11, coluna 9 (0-indexed)
        df_ref = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto = str(df_ref.iloc[11, 0])
        match = re.search(r'(\d+)', texto)
        return int(match.group(1)) if match else 999
    except:
        return 999

def formatar_br(valor):
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 2. PROCESSAMENTO PRINCIPAL ---

if uploaded_files:
    # Ordenação cronológica das planilhas
    files_sorted = sorted(uploaded_files, key=extrair_ordem_j12)
    
    # Este DataFrame será o nosso esqueleto que cresce dinamicamente
    df_consolidado = pd.DataFrame()
    
    # Mapeamento de colunas (Excel para Índice 0-based)
    # A=0, J=9, AD=29, AI=34, AO=40, AU=46, BI=60, CF=83
    cols_indices = [0, 9, 29, 34, 40, 46, 60, 83]
    cols_nomes = ['COD', 'SERVICO', 'UNID', 'VAL_UNIT', 'QTD_CONTRATADA', 'QTD_MED', 'VAL_MED', 'REAJUSTE']

    for file in files_sorted:
        n_bm = extrair_ordem_j12(file)
        label = f"BM_{n_bm:02d}"
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        
        # Lendo a planilha a partir da linha 26 (skiprows=25)
        df_atual = pd.read_excel(file, skiprows=25, header=None, engine=engine)
        df_atual = df_atual.iloc[:, cols_indices]
        df_atual.columns = cols_nomes

        # --- FILTRO DE FIM DE PLANILHA ---
        # Localiza "TOTAL MÃO-DE-OBRA" na coluna A (índice 0)
        linha_fim = df_atual[df_atual['COD'].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_fim.empty:
            df_atual = df_atual.iloc[:linha_fim[0]]

        # --- IDENTIFICAÇÃO DE UNIDADE CONSTRUTIVA E CHAVE ÚNICA ---
        # Requisito: UC tem UNID vazia.
        # Para evitar erro de nomes iguais em UCs diferentes, criamos uma chave hierárquica
        uc_atual = ""
        chaves = []
        
        for i, row in df_atual.iterrows():
            is_uc = pd.isna(row['UNID']) or str(row['UNID']).strip() == ""
            servico_nome = str(row['SERVICO']).strip()
            
            if is_uc:
                uc_atual = servico_nome
            
            # Chave: Unidade Construtiva + Código + Nome do Serviço
            # O .cumcount() resolve o problema de itens idênticos na mesma UC
            chaves.append(f"{uc_atual}_{row['COD']}_{servico_nome}")

        df_atual['CHAVE_UNICA'] = chaves
        # Adiciona contador para chaves duplicadas (ex: vários itens de pavimentação na mesma UC)
        df_atual['CHAVE_UNICA'] += "_" + df_atual.groupby('CHAVE_UNICA').cumcount().astype(str)

        # Selecionamos apenas o necessário para o merge
        # Mantemos COD, SERVICO, UNID, VAL_UNIT, QTD_CONTRATADA apenas do arquivo mais recente
        medicao_cols = df_atual[['CHAVE_UNICA', 'QTD_MED', 'VAL_MED', 'REAJUSTE']].copy()
        medicao_cols.columns = ['CHAVE_UNICA', f'QTD_{label}', f'VAL_{label}', f'REAJ_{label}']

        if df_consolidado.empty:
            # Primeira planilha define o esqueleto inicial
            df_consolidado = df_atual[['CHAVE_UNICA', 'COD', 'SERVICO', 'UNID', 'VAL_UNIT', 'QTD_CONTRATADA']].copy()
            df_consolidado = pd.merge(df_consolidado, medicao_cols, on='CHAVE_UNICA', how='left')
        else:
            # MERGE EXTERNO (how='outer'): Se houver item novo (Aditivo), ele entra no esqueleto
            # Se o item sumir, ele fica com NaN (que trataremos como zero)
            df_consolidado = pd.merge(df_consolidado, medicao_cols, on='CHAVE_UNICA', how='outer')
            
            # Se for uma linha nova, as informações básicas (COD, SERVICO...) vêm da planilha atual
            # Atualizamos as informações mestre para as linhas que eram NaN (novas)
            for col in ['COD', 'SERVICO', 'UNID', 'VAL_UNIT', 'QTD_CONTRATADA']:
                df_consolidado[col] = df_consolidado[col].combine_first(df_consolidado['CHAVE_UNICA'].map(df_atual.set_index('CHAVE_UNICA')[col]))

    # --- 3. CONSOLIDAÇÃO DOS TOTAIS ---

    # Preenche vazios com zero (itens novos em medições antigas ou itens removidos)
    df_consolidado = df_consolidado.fillna(0)

    # Identifica colunas para soma
    col_qtd_todas = [c for c in df_consolidado.columns if 'QTD_BM' in c]
    col_val_todas = [c for c in df_consolidado.columns if 'VAL_BM' in c]
    col_reaj_todas = [c for c in df_consolidado.columns if 'REAJ_BM' in c]

    df_consolidado['TOTAL_QTD'] = df_consolidado[col_qtd_todas].sum(axis=1)
    df_consolidado['TOTAL_VALOR'] = df_consolidado[col_val_todas].sum(axis=1)
    df_consolidado['TOTAL_REAJUSTE'] = df_consolidado[col_reaj_todas].sum(axis=1)
    df_consolidado['TOTAL_GERAL'] = df_consolidado['TOTAL_VALOR'] + df_consolidado['TOTAL_REAJUSTE']

    # --- 4. EXIBIÇÃO E CURVA ABC ---

    st.subheader("📊 Histórico Consolidado")
    # Removemos a chave única técnica da visão do usuário
    df_view = df_consolidado.drop(columns=['CHAVE_UNICA'])
    
    # Formatação para exibição
    cols_num = df_view.select_dtypes(include=['number']).columns
    st.dataframe(df_view.style.format({c: formatar_br for c in cols_num}), use_container_width=True)

    # --- ABA CURVA ABC ---
    st.divider()
    st.subheader("📈 Curva ABC (Somente Serviços)")

    # Filtro: Apenas serviços (UNID preenchida e VAL_UNIT > 0)
    abc = df_consolidado[
        (df_consolidado['UNID'] != 0) & 
        (df_consolidado['UNID'] != "") & 
        (df_consolidado['TOTAL_GERAL'] > 0)
    ].copy()

    if not abc.empty:
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        total_obra = abc['TOTAL_GERAL'].sum()
        abc['PART_PERC'] = (abc['TOTAL_GERAL'] / total_obra) * 100
        abc['ACC_PERC'] = abc['PART_PERC'].cumsum()
        
        abc['CLASSE'] = abc['ACC_PERC'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

        st.write(f"**Valor Total Considerado para ABC:** R$ {formatar_br(total_obra)}")
        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'TOTAL_GERAL', 'PART_PERC', 'ACC_PERC', 'CLASSE']]
            .style.format({
                'TOTAL_GERAL': formatar_br,
                'PART_PERC': "{:.2f}%",
                'ACC_PERC': "{:.2f}%"
            }), use_container_width=True
        )

    # --- EXPORTAÇÃO ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_view.to_excel(writer, sheet_name='Historico', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='CurvaABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório Consolidado", output.getvalue(), "historico_obra_abc.xlsx")
