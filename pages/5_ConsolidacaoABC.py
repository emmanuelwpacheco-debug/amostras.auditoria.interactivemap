import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico (Versão Aditivos)")

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

    # 1. Esqueleto Base (Última Medição com Aditivos)
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        
        linha_corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_corte.empty:
            df_m = df_m.iloc[:linha_corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        df_m = df_m.loc[:, ~df_m.columns.str.contains('UNNAMED|NAN', case=False)]
        
        c_cod = df_m.columns[0]
        c_serv = df_m.columns[1]
        c_unid = next((c for c in df_m.columns if 'UNID' in c), df_m.columns[2])
        c_precu = next((c for c in df_m.columns if 'UNIT' in c), df_m.columns[3])
        c_qtd_orc = next((c for c in df_m.columns if 'CONTRATADA' in c or 'QTD. ORC' in c), df_m.columns[4])
        
        resultado = df_m[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # Criamos a CHAVE MESTRA (Código + Serviço) para o join não depender da posição da linha
        resultado['CHAVE_JOIN'] = resultado['COD'].astype(str).strip() + resultado['SERVICO'].astype(str).strip()
        # Guardamos a ordem original para re-exibir corretamente ao final
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        
    except Exception as e:
        st.error(f"Erro na estrutura mestre: {e}")
        st.stop()

    # 2. Integração de Dados por "Matching" de Código/Serviço
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            label = item['label']
            
            # Localizar colunas
            cols_med = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            
            # Criar chave no arquivo da medição atual
            df_bm['CHAVE_JOIN'] = df_bm.iloc[:, 0].astype(str).strip() + df_bm.iloc[:, 1].astype(str).strip()
            
            med_cols = pd.DataFrame()
            med_cols['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            
            if len(cols_med) >= 2:
                med_cols[f'QTD_{label}'] = pd.to_numeric(df_bm[cols_med[0]], errors='coerce').fillna(0)
                med_cols[f'VALOR_{label}'] = pd.to_numeric(df_bm[cols_med[1]], errors='coerce').fillna(0)
            if c_reaj:
                med_cols[f'REAJ_{label}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0)
            
            # O join agora é 'left' (quem manda é o esqueleto mestre) e baseado na chave do serviço
            resultado = pd.merge(resultado, med_cols, on='CHAVE_JOIN', how='left')
            
        except Exception as e:
            st.warning(f"Erro no matching do arquivo {item['file'].name}: {e}")

    # 3. Consolidação e Limpeza
    # Remove duplicatas de join se houver (segurança)
    resultado = resultado.drop_duplicates(subset=['CHAVE_JOIN'], keep='first')
    # Ordena de volta para a estrutura fidedigna do orçamento
    resultado = resultado.sort_values('ORDEM_ORIGINAL').drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL']).fillna(0)
    
    c_qtds = [c for c in resultado.columns if 'QTD_' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- TELA: HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado com Aditivos ({len(processados)} Medições)")
    colunas_numericas = resultado.select_dtypes(include=['float64', 'int64']).columns
    format_dict_br = {col: formatar_br for col in colunas_numericas}

    def format_rows(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    st.dataframe(resultado.style.apply(format_rows, axis=1).format(format_dict_br), use_container_width=True)

    # --- ABA: CURVA ABC ---
    st.divider()
    st.subheader("📈 Análise de Curva ABC")
    
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01]
    
    if not abc.empty:
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        
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

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(total_pi_abc)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(total_reajuste_abc)}")
        m3.metric("Total Global", f"R$ {formatar_br(total_global_abc)}")
        m4.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', '%_ACUMULADO', 'CLASSE']]
            .style.format({
                'VALOR_ACUMULADO': formatar_br,
                'REAJUSTE_ACUMULADO': formatar_br,
                'TOTAL_GERAL': formatar_br,
                '%_ACUMULADO': "{:.2f}%"
            }).applymap(lambda v: f'color: {"#d9534f" if v=="A" else ("#f0ad4e" if v=="B" else "#5cb85c")}; font-weight: bold', subset=['CLASSE']),
            use_container_width=True
        )

    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        resultado.to_excel(writer, sheet_name='Historico_Final', index=False)
    st.sidebar.download_button("📥 Baixar Relatório Final", output.getvalue(), "relatorio_final_aditivo.xlsx")
