import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import get_close_matches

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

# --- FUNÇÕES DE APOIO ---
def normalizar_texto(txt):
    """Limpeza pesada para garantir o match entre medições"""
    if pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    txt = re.sub(r'[^A-Z0-9]', '', txt) # Mantém apenas alfanuméricos
    return txt

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

# --- PROCESSAMENTO ---
if uploaded_files:
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # 1. Esqueleto Base (Última Medição)
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        
        # Corte na linha "TOTAL MÃO-DE-OBRA"
        linha_corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA|TOTAL GERAL", case=False, na=False)].index
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
        
        # Chave para o Matching
        resultado['CHAVE_LIMPA'] = (resultado['COD'].apply(normalizar_texto) + 
                                   resultado['SERVICO'].apply(normalizar_texto))
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        lista_chaves_mestre = resultado['CHAVE_LIMPA'].tolist()
        
    except Exception as e:
        st.error(f"Erro na estrutura mestre: {e}")
        st.stop()

    # 2. Integração de Dados com Fuzzy Match
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]
            label = item['label']
            
            # Criar chave temporária na medição
            df_bm['CHAVE_ATUAL'] = (df_bm.iloc[:, 0].apply(normalizar_texto) + 
                                    df_bm.iloc[:, 1].apply(normalizar_texto))
            
            # Lógica para encontrar o item correspondente no esqueleto mestre
            def buscar_correspondencia(chave):
                if not chave: return None
                if chave in lista_chaves_mestre: return chave
                # Tenta similaridade de 90% para evitar erros de digitação ou espaços
                match = get_close_matches(chave, lista_chaves_mestre, n=1, cutoff=0.9)
                return match[0] if match else None

            df_bm['CHAVE_JOIN'] = df_bm['CHAVE_ATUAL'].apply(buscar_correspondencia)
            
            cols_med = [c for c in df_bm.columns if 'DA MEDIÇÃO' in c]
            c_reaj = next((c for c in df_bm.columns if 'REAJUSTE' in c or 'REAJUSTAMENTO' in c), None)
            
            med_resumo = pd.DataFrame()
            med_resumo['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            if len(cols_med) >= 2:
                med_resumo[f'QTD_{label}'] = pd.to_numeric(df_bm[cols_med[0]], errors='coerce').fillna(0)
                med_resumo[f'VALOR_{label}'] = pd.to_numeric(df_bm[cols_med[1]], errors='coerce').fillna(0)
            if c_reaj:
                med_resumo[f'REAJ_{label}'] = pd.to_numeric(df_bm[c_reaj], errors='coerce').fillna(0)
            
            # Agrupa para evitar duplicatas e faz o merge
            med_resumo = med_resumo.dropna(subset=['CHAVE_JOIN']).groupby('CHAVE_JOIN').sum().reset_index()
            resultado = pd.merge(resultado, med_resumo, left_on='CHAVE_LIMPA', right_on='CHAVE_JOIN', how='left').drop(columns=['CHAVE_JOIN'])
            
        except Exception as e:
            st.warning(f"Aviso no arquivo {item['file'].name}: {e}")

    # 3. Consolidação Final
    resultado = resultado.sort_values('ORDEM_ORIGINAL').fillna(0)
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- VISUALIZAÇÃO DO HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    colunas_num = resultado.select_dtypes(include=['float64', 'int64']).columns
    format_dict_br = {col: formatar_br for col in colunas_num}

    def estilo_linhas(row):
        if row['PRECO_UNIT'] == 0:
            return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        return [''] * len(row)

    df_final_view = resultado.drop(columns=['CHAVE_LIMPA', 'ORDEM_ORIGINAL'])
    st.dataframe(df_final_view.style.apply(estilo_linhas, axis=1).format(format_dict_br), use_container_width=True)

    # --- CURVA ABC ---
    st.divider()
    abc = resultado[resultado['PRECO_UNIT'] > 0].copy()
    abc = abc[abc['TOTAL_GERAL'] > 0.01]
    
    if not abc.empty:
        st.subheader("📈 Análise de Curva ABC (Serviços)")
        abc = abc.sort_values(by='TOTAL_GERAL', ascending=False)
        
        t_pi = abc['VALOR_ACUMULADO'].sum()
        t_reaj = abc['REAJUSTE_ACUMULADO'].sum()
        t_global = abc['TOTAL_GERAL'].sum()
        
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / t_global) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(lambda p: 'A' if p <= 80.01 else ('B' if p <= 95.01 else 'C'))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Serviços (PI)", f"R$ {formatar_br(t_pi)}")
        m2.metric("Total Reajuste", f"R$ {formatar_br(t_reaj)}")
        m3.metric("Total Global", f"R$ {formatar_br(t_global)}")
        m4.metric("Itens Classe A", f"{len(abc[abc['CLASSE'] == 'A'])}")

        def color_classe(val):
            color = '#d9534f' if val == 'A' else ('#f0ad4e' if val == 'B' else '#5cb85c')
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            abc[['COD', 'SERVICO', 'UNID', 'VALOR_ACUMULADO', 'REAJUSTE_ACUMULADO', 'TOTAL_GERAL', '%_ACUMULADO', 'CLASSE']]
            .style.format({
                'VALOR_ACUMULADO': formatar_br, 'REAJUSTE_ACUMULADO': formatar_br, 
                'TOTAL_GERAL': formatar_br, '%_ACUMULADO': "{:.2f}%"
            }).applymap(color_classe, subset=['CLASSE']),
            use_container_width=True
        )

    # Exportação
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final_view.to_excel(writer, sheet_name='Historico_Geral', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    st.sidebar.download_button("📥 Baixar Relatório Final", output.getvalue(), "relatorio_goinfra_consolidado.xlsx")
