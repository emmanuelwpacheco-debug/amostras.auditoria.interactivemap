import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
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
        return 999, "BM_Erro"
    except:
        return 999, "BM_Erro"

# Função para formatar números no padrão brasileiro (###.###,00)
def formatar_br(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # --- INÍCIO DA SUBSTITUIÇÃO ---

   # 1. ESQUELETO MESTRE (Coluna B=Código, Coluna J=Serviço)
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        # Lemos a partir da linha 26 (skiprows=25)
        df_raw = pd.read_excel(ultimo_item['file'], skiprows=25, header=None, engine=eng_m)
        
        # Filtro de rodapé: para quando encontrar "TOTAL" na primeira ou segunda coluna
        linha_corte = df_raw[df_raw.iloc[:, 0].astype(str).str.contains("TOTAL|MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_corte.empty:
            df_raw = df_raw.iloc[:linha_corte[0]]

        # Mapeamento Direto por Índices (Padrão GOINFRA)
        # B=1 (Cód), J=9 (Descrição), K=10 (Unid), L=11 (Preço), M=12 (Qtd Contratada)
        resultado = pd.DataFrame()
        resultado['COD'] = df_raw.iloc[:, 1].astype(str).replace('nan', '').str.strip()
        resultado['SERVICO'] = df_raw.iloc[:, 9].astype(str).replace('nan', '').str.strip()
        resultado['UNID'] = df_raw.iloc[:, 10].astype(str).replace('nan', '').str.strip()
        resultado['PRECO_UNIT'] = pd.to_numeric(df_raw.iloc[:, 11], errors='coerce').fillna(0)
        resultado['QTD_ORC'] = pd.to_numeric(df_raw.iloc[:, 12], errors='coerce').fillna(0)
        
        # DNA único para não perder o rastro no aditivo
        resultado['CHAVE_JOIN'] = resultado['COD'] + "_" + resultado['SERVICO']
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))

    except Exception as e:
        st.error(f"Erro ao ler a estrutura da Coluna J: {e}")
        st.stop()

    # 2. INTEGRAÇÃO DAS MEDIÇÕES (Busca apenas os valores)
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, header=None, engine=eng)
            label = item['label']
            
            # Mesma chave de busca (B + J)
            df_bm['CHAVE_JOIN'] = (
                df_bm.iloc[:, 1].astype(str).str.strip() + "_" + 
                df_bm.iloc[:, 9].astype(str).str.strip()
            )
            
            # Dados da Medição: Geralmente Qtd está na Coluna P(15) e Valor na Q(16)
            # Mas vamos buscar a coluna que tem o valor monetário da medição
            med_dados = pd.DataFrame()
            med_dados['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            
            # Procura a coluna de valor da medição (normalmente 2 colunas após a Qtd Contratada)
            # Na GOINFRA padrão: Coluna P = 15 (Qtd Medida), Coluna Q = 16 (Valor Medido)
            med_dados[f'QTD_{label}'] = pd.to_numeric(df_bm.iloc[:, 15], errors='coerce').fillna(0)
            med_dados[f'VALOR_{label}'] = pd.to_numeric(df_bm.iloc[:, 16], errors='coerce').fillna(0)
            
            # Remove duplicatas e une ao mestre
            med_dados = med_dados.drop_duplicates(subset=['CHAVE_JOIN'])
            resultado = pd.merge(resultado, med_dados, on='CHAVE_JOIN', how='left')
        except:
            st.warning(f"Não foi possível processar a {label}")

    # 3. CONSOLIDAÇÃO FINAL
    resultado = resultado.sort_values('ORDEM_ORIGINAL').fillna(0)
    
    # Cálculos de Acumulado
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    resultado['TOTAL_GERAL'] = resultado[c_vals].sum(axis=1)

    # Limpeza de colunas técnicas
    df_view = resultado.drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL'])

    # --- EXIBIÇÃO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")

    # Formatação de Moeda apenas para colunas numéricas (ignora a Coluna J/Serviço)
    cols_float = df_view.select_dtypes(include=['float64', 'int64']).columns
    format_rules = {c: formatar_br for c in cols_float}

    # FUNÇÃO DE ESTILO CORRIGIDA (O erro do traceback estava aqui)
    def style_row(row):
        # Se o preço unitário for zero, é um Título/Cabeçalho
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; color: #1f77b4; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_view.style.apply(style_row, axis=1).format(format_rules),
        use_container_width=True
    )

    # --- ABA: CURVA ABC ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC (Somente Serviços)")
    
    # IMPORTANTE: Filtramos apenas serviços reais para a ABC
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01]
    
    if not abc.empty:
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        
        # Somas baseadas apenas nos serviços (evita duplicidade dos títulos)
        total_pi_abc = abc['VALOR_ACUMULADO'].sum()
        total_reajuste_abc = abc['REAJUSTE_ACUMULADO'].sum()
        total_global_abc = abc['TOTAL_GERAL'].sum()
        
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / total_global_abc) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        
        def classificar_abc(porc):
            if porc <= 80.01: return 'A'
            if porc <= 95.01: return 'B'
            return 'C'
        
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(classificar_abc)

        # Resumo Financeiro Corrigido
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(total_pi_abc)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(total_reajuste_abc)}")
        m3.metric("Total Global (PI + Reaj)", f"R$ {formatar_br(total_global_abc)}")
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
            })
            .applymap(color_classe, subset=['CLASSE']),
            use_container_width=True
        )

    # Exportação Final
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        resultado.to_excel(writer, sheet_name='Historico_Limpo', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório Final (Excel)", output.getvalue(), "relatorio_goinfra_limpo.xlsx")
