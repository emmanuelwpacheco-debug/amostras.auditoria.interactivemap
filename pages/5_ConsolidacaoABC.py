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

    # 1. ESQUELETO MESTRE (A "Verdade" vem daqui)
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        
        # Corte de rodapé
        linha_corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_corte.empty:
            df_m = df_m.iloc[:linha_corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        
        # --- NOVO MAPEAMENTO FIXO (GOINFRA) ---
        # Usamos .columns[i] para garantir que pegamos a coluna física correta
        c_cod  = df_m.columns[0]   # Coluna A/B (Código)
        c_serv = df_m.columns[9]   # COLUNA J (Descrição) - Índice 9
        
        # Busca dinâmica para as demais, ou índices fixos se falhar
        c_unid = next((c for c in df_m.columns if 'UNID' in str(c).upper()), df_m.columns[10])
        c_precu = next((c for c in df_m.columns if 'UNIT' in str(c).upper()), df_m.columns[11])
        c_qtd_orc = next((c for c in df_m.columns if 'CONTRATADA' in str(c).upper() or 'QTD. ORC' in str(c).upper()), df_m.columns[12])
        
        resultado = df_m[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # Limpeza para evitar que 'nan' vire texto
        resultado['SERVICO'] = resultado['SERVICO'].astype(str).replace(['nan', '0', '0.0', 'None'], '')
        
        # CHAVE_JOIN baseada na nova coluna SERVICO (Coluna J)
       resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        resultado['CHAVE_JOIN'] = resultado['ORDEM_ORIGINAL'].astype(str) + "_" + \
                                  resultado['COD'].astype(str).str.strip()
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))

    except Exception as e:
        st.error(f"Erro ao montar esqueleto da última medição: {e}")
        st.stop()

    # 2. INTEGRAÇÃO DOS VALORES (Buscamos apenas números nas outras BMs)
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            label = item['label']
            
            # Criamos um DataFrame temporário para a medição atual
            temp_med = pd.DataFrame()
            
            # Identificamos a posição de cada serviço na planilha atual
            temp_med['COD_TEMP'] = df_bm.iloc[:, 0].astype(str).str.strip()
            temp_med['VALOR_UNIT_TEMP'] = pd.to_numeric(df_bm.iloc[:, 11], errors='coerce').fillna(0)
            
            # COLUNAS DE VALOR (Índice 16) e REAJUSTE (Índice 18)
            temp_med[f'VALOR_{label}'] = pd.to_numeric(df_bm.iloc[:, 16], errors='coerce').fillna(0)
            temp_med[f'REAJ_{label}'] = pd.to_numeric(df_bm.iloc[:, 18], errors='coerce').fillna(0)
            
            # A MÁGICA: Criamos a CHAVE_JOIN baseada na posição (index) 
            # Isso garante que a 2ª "Pavimentação" da BM pegue a 2ª "Pavimentação" do Mestre
            temp_med['CHAVE_JOIN'] = temp_med.index.astype(str) + "_" + temp_med['COD_TEMP']
            
            # Selecionamos apenas as colunas de dados
            temp_med = temp_med[['CHAVE_JOIN', f'VALOR_{label}', f'REAJ_{label}']]
            
            # Merge exato pela posição
            resultado = pd.merge(resultado, temp_med, on='CHAVE_JOIN', how='left')
            
        except Exception as e:
            st.warning(f"Erro ao integrar {item['label']}: {e}")

    # 3. CONSOLIDAÇÃO E LIMPEZA (A prova de falhas)
    
    # Mantém a ordem da última planilha

    # 1. Identifica colunas de texto e limpa valores fantasmas
    for col in ['COD', 'SERVICO', 'UNID']:
        resultado[col] = resultado[col].astype(str).replace(['nan', '0', '0.0', 'None'], '')

    # 2. Identifica colunas numéricas e zera os valores nulos
    cols_numericas = resultado.select_dtypes(include=['number']).columns
    resultado[cols_numericas] = resultado[cols_numericas].fillna(0)

    # Identifica o que é número e o que é texto
    cols_numericas = resultado.select_dtypes(include=['number']).columns
    # Zera apenas onde deve haver números
    resultado[cols_numericas] = resultado[cols_numericas].fillna(0)
    # Garante que textos fiquem como string (evita o erro de sumir ou virar 0,00)
    resultado = resultado.fillna("")

    # Cálculos Finais
    c_qtds = [c for c in resultado.columns if 'QTD_BM' in c]
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['QTD_ACUMULADA'] = resultado[c_qtds].sum(axis=1)
    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # Criamos o dataframe final de exibição removendo as colunas de controle
    df_exibicao = resultado.drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL'])

    # --- TELA: HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    
    # Formatação condicional para os números
    format_dict = {col: formatar_br for col in df_exibicao.select_dtypes(include=['number']).columns}

    def destacar_titulos(row):
        try:
            # Se for título (Preço Unitário zero ou vazio), destaca em azul
            p_unit = float(row['PRECO_UNIT']) if row['PRECO_UNIT'] != "" else 0
            if p_unit == 0:
                return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        except: pass
        return [''] * len(row)

    st.dataframe(
        df_exibicao.style.apply(destacar_titulos, axis=1).format(format_dict),
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
