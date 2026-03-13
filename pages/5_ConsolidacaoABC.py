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

# --- FUNÇÕES DE UTILIDADE ---
def normalizar_para_busca(txt):
    """Limpa o texto para garantir que o 'match' ocorra mesmo com espaços ou acentos diferentes"""
    if pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    txt = re.sub(r'\s+', ' ', txt) # Remove espaços duplos
    return txt

def formatar_br(valor):
    """Formatação padrão brasileiro: 1.250,50"""
    if pd.isna(valor) or valor == 0: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_cab = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        num = re.findall(r'(\d+)', str(df_cab.iloc[11, 0]))
        if num:
            n = int(num[0])
            return n, f"BM_{n:02d}"
        return 999, "BM_Erro"
    except:
        return 999, "BM_Erro"

# --- PROCESSAMENTO PRINCIPAL ---
if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. CRIAR O ESQUELETO MESTRE (Baseado na última medição - Aditivada)
    try:
        u_item = processados[-1]
        eng_u = 'xlrd' if u_item['file'].name.endswith('.xls') else 'openpyxl'
        df_mestre_raw = pd.read_excel(u_item['file'], skiprows=25, engine=eng_u)
        
        # Corte dinâmico para remover resumos de impostos/mão de obra abaixo da tabela
        corte = df_mestre_raw[df_mestre_raw.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA|TOTAL GERAL", case=False, na=False)].index
        if not corte.empty:
            df_mestre_raw = df_mestre_raw.iloc[:corte[0]]

        df_mestre_raw.columns = [str(c).strip().upper() for c in df_mestre_raw.columns]
        
        # Colunas fundamentais do orçamento
        resultado = df_mestre_raw.iloc[:, [0, 1, 2, 3, 4]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # Coluna invisível para busca (chave de comparação)
        resultado['KEY_BUSCA'] = resultado['SERVICO'].apply(normalizar_para_busca)
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        
    except Exception as e:
        st.error(f"Erro ao estruturar orçamento mestre: {e}")
        st.stop()

    # 2. BUSCA DINÂMICA (ALIMENTANDO O HISTÓRICO)
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_atual = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_atual.columns = [str(c).strip().upper() for c in df_atual.columns]
            
            # Localiza colunas de valores (geralmente as que contêm 'DA MEDIÇÃO')
            cols_med = [c for c in df_atual.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_atual.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            
            # Prepara a planilha da medição atual para busca
            df_atual['KEY_BUSCA'] = df_atual.iloc[:, 1].apply(normalizar_para_busca)
            
            # Cria dicionários de busca (Catálogo da Medição)
            dict_qtd = pd.Series(df_atual[cols_med[0]].values, index=df_atual['KEY_BUSCA']).to_dict()
            dict_val = pd.Series(df_atual[cols_med[1]].values, index=df_atual['KEY_BUSCA']).to_dict()
            dict_reaj = {}
            if c_reaj:
                dict_reaj = pd.Series(df_atual[c_reaj].values, index=df_atual['KEY_BUSCA']).to_dict()

            # Mapeia os dados para a tabela principal usando a KEY_BUSCA
            resultado[f'QTD_{item["label"]}'] = resultado['KEY_BUSCA'].map(dict_qtd).fillna(0)
            resultado[f'VALOR_{item["label"]}'] = resultado['KEY_BUSCA'].map(dict_val).fillna(0)
            resultado[f'REAJ_{item["label"]}'] = resultado['KEY_BUSCA'].map(dict_reaj).fillna(0)
            
        except Exception as e:
            st.warning(f"Erro ao ler {item['label']}: {e}")

    # 3. CÁLCULOS TOTAIS
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- ABA: HISTÓRICO (VISUALIZAÇÃO) ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    df_visual = resultado.sort_values('ORDEM_ORIGINAL').drop(columns=['KEY_BUSCA', 'ORDEM_ORIGINAL'])
    
    def estilo_tabela(row):
        # Títulos (Preço Unitário == 0) ficam em destaque
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_visual.style.apply(estilo_tabela, axis=1)
        .format({c: formatar_br for c in df_visual.select_dtypes(include=['float64', 'int64']).columns}),
        use_container_width=True
    )

    # --- ABA: CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01]
    
    if not abc.empty:
        st.subheader("📈 Análise de Curva ABC (Somente Serviços)")
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        
        t_pi = abc['VALOR_ACUMULADO'].sum()
        t_reaj = abc['REAJUSTE_ACUMULADO'].sum()
        t_global = abc['TOTAL_GERAL'].sum()
        
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / t_global) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(lambda p: 'A' if p <= 80.01 else ('B' if p <= 95.01 else 'C'))

        # Métricas em colunas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(t_pi)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(t_reaj)}")
        m3.metric("Total Global (PI + Reaj)", f"R$ {formatar_br(t_global)}")
        m4.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")

        def color_classe(val):
            color = '#d9534f' if val == 'A' else ('#f0ad4e' if val == 'B' else '#5cb85c')
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', '%_ACUMULADO', 'CLASSE']]
            .style.format({
                'VALOR_ACUMULADO': formatar_br, 
                'REAJUSTE_ACUMULADO': formatar_br, 
                'TOTAL_GERAL': formatar_br, 
                '%_ACUMULADO': "{:.2f}%"
            }).applymap(color_classe, subset=['CLASSE']),
            use_container_width=True
        )

    # --- EXPORTAÇÃO ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_visual.to_excel(writer, sheet_name='Historico_Geral', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório Consolidado (Excel)", output.getvalue(), "consolidado_goinfra_final.xlsx")
