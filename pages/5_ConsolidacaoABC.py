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
# --- 1. ESQUELETO MESTRE (A "Verdade" vem daqui) ---
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        # Lemos sem cortar o rodapé agora, para preservar as linhas de TOTAL
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, header=None, engine=eng_m)
        
        # Em vez de cortar, limpamos apenas linhas completamente vazias no final
        df_m = df_m.dropna(how='all', subset=[0, 1, 9]) 

        # Mapeamento por índices fixos (Padrão GOINFRA)
        # B=1 (Cód), J=9 (Serviço), K=10 (Unid), L=11 (Preço Unit), M=12 (Qtd Orc)
        resultado = pd.DataFrame()
        resultado['COD'] = df_m.iloc[:, 1].astype(str).replace('nan', '').str.strip()
        resultado['SERVICO'] = df_m.iloc[:, 9].astype(str).replace('nan', '').str.strip()
        resultado['UNID'] = df_m.iloc[:, 10].astype(str).replace('nan', '').str.strip()
        resultado['PRECO_UNIT'] = pd.to_numeric(df_m.iloc[:, 11], errors='coerce').fillna(0)
        resultado['QTD_ORC'] = pd.to_numeric(df_m.iloc[:, 12], errors='coerce').fillna(0)
        
        # Chave de ligação robusta
        resultado['CHAVE_JOIN'] = resultado['COD'] + "_" + resultado['SERVICO']
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))

    except Exception as e:
        st.error(f"Erro ao processar estrutura mestre: {e}")
        st.stop()

    # --- 2. INTEGRAÇÃO DOS VALORES ---
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, header=None, engine=eng)
            label = item['label']
            
            # Criamos a chave idêntica para o "match"
            df_bm['CHAVE_JOIN'] = (
                df_bm.iloc[:, 1].astype(str).str.strip() + "_" + 
                df_bm.iloc[:, 9].astype(str).str.strip()
            )
            
            med_dados = pd.DataFrame()
            med_dados['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            
            # Índices GOINFRA: P(15)=Qtd, Q(16)=Valor, R(17) ou S(18)=Reajuste
            # Tentamos localizar a coluna de reajuste pelo cabeçalho ou índice fixo
            med_dados[f'QTD_{label}'] = pd.to_numeric(df_bm.iloc[:, 15], errors='coerce').fillna(0)
            med_dados[f'VALOR_{label}'] = pd.to_numeric(df_bm.iloc[:, 16], errors='coerce').fillna(0)
            med_dados[f'REAJ_{label}'] = pd.to_numeric(df_bm.iloc[:, 18], errors='coerce').fillna(0)
            
            med_dados = med_dados.drop_duplicates(subset=['CHAVE_JOIN'])
            resultado = pd.merge(resultado, med_dados, on='CHAVE_JOIN', how='left')
        except:
            st.warning(f"Aviso: Falha na integração da {label}")

    # --- 3. CONSOLIDAÇÃO E CÁLCULO DE TOTAIS ---
    resultado = resultado.sort_values('ORDEM_ORIGINAL').fillna(0)
    
    # Identificamos colunas para soma
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Criamos uma linha de TOTAL CALCULADO para conferência (Soma apenas serviços com PRECO > 0)
    # Isso evita somar os subtotais que o Excel já traz
    servicos_reais = resultado[(resultado['PRECO_UNIT'] > 0) & (resultado['UNID'] != "")]
    totais_soma = servicos_reais.select_dtypes(include=['number']).sum()
    
    linha_resumo = pd.Series(dtype='object')
    linha_resumo['SERVICO'] = "TOTAL GERAL DA OBRA (SOMA DOS SERVIÇOS)"
    for col in totais_soma.index:
        linha_resumo[col] = totais_soma[col]
    
    df_exibicao_final = pd.concat([resultado, linha_resumo.to_frame().T], ignore_index=True)

    # --- TELA: HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    df_view = df_exibicao_final.drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL'])
    cols_num = df_view.select_dtypes(include=['number']).columns

    def destacar_estilo(row):
        if "TOTAL GERAL DA OBRA" in str(row['SERVICO']):
            return ['background-color: #1f77b4; color: white; font-weight: bold'] * len(row)
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_view.style.apply(destacar_estilo, axis=1).format({c: formatar_br for c in cols_num}),
        use_container_width=True
    )

    # --- ABA: CURVA ABC (Correção de Duplicidade) ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC (Somente Serviços Reais)")
    
    # Filtro Crítico: Para a ABC ser exata, só entram itens com Unidade e Preço
    # Isso ignora automaticamente Títulos, Subtotais e a linha de Total Geral
    abc = resultado[(resultado['PRECO_UNIT'] > 0) & (resultado['UNID'] != "")].copy()
    
    if not abc.empty:
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        total_pi_abc = abc['VALOR_ACUMULADO'].sum()
        total_reaj_abc = abc['REAJUSTE_ACUMULADO'].sum()
        total_global_abc = total_pi_abc + total_reaj_abc
        
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / total_global_abc) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(lambda x: 'A' if x <= 80.01 else ('B' if x <= 95.01 else 'C'))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(total_pi_abc)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(total_reaj_abc)}")
        m3.metric("Total Global (PI + Reaj)", f"R$ {formatar_br(total_global_abc)}")
        m4.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', '%_ACUMULADO', 'CLASSE']]
            .style.format({
                'VALOR_ACUMULADO': formatar_br, 
                'REAJUSTE_ACUMULADO': formatar_br, 
                'TOTAL_GERAL': formatar_br, 
                '%_ACUMULADO': "{:.2f}%"
            }),
            use_container_width=True
        )

    # Exportação Final
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_view.to_excel(writer, sheet_name='Historico_Consolidado', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório Final", output.getvalue(), "relatorio_consolidado.xlsx")
