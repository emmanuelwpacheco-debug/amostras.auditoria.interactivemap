import streamlit as st
import pandas as pd
import ioimport streamlit as st
import pandas as pd
import io
import re

# Configuração da página para ocupar a tela toda
st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

# Barra lateral para upload
uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

# --- FUNÇÃO: Identificar o número da BM no cabeçalho (Célula J12) ---
def extrair_id_medicao(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        # Lemos apenas a parte do cabeçalho
        df_cabecalho = pd.read_excel(file, nrows=12, usecols="J", header=None, engine=engine)
        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()
        numeros = re.findall(r'(\d+)', texto_j12)
        if numeros:
            num = int(numeros[0])
            return num, f"BM_{num:02d}"
        return 999, "BM_Erro"
    except:
        return 999, "BM_Erro"

# --- FUNÇÃO: Formatação de Moeda Brasileira ---
def formatar_br(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if uploaded_files:
    # Organização dos arquivos por ordem cronológica
    processados = []
    for file in uploaded_files:
        ordem, label = extrair_id_medicao(file)
        processados.append({'file': file, 'ordem': ordem, 'label': label})
    
    processados = sorted(processados, key=lambda x: x['ordem'])

    # --- 1. ESQUELETO MESTRE (Cria a base da tabela usando a última BM) ---
    try:
        ultimo_item = processados[-1]
        eng_m = 'xlrd' if ultimo_item['file'].name.endswith('.xls') else 'openpyxl'
        # Pulamos as 25 linhas de cabeçalho da GOINFRA
        df_m = pd.read_excel(ultimo_item['file'], skiprows=25, engine=eng_m)
        
        # Removemos o rodapé de assinaturas para não sujar os dados
        linha_corte = df_m[df_m.iloc[:, 0].astype(str).str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)].index
        if not linha_corte.empty:
            df_m = df_m.iloc[:linha_corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        
        # Mapeamento das colunas essenciais
        c_cod  = df_m.columns[0]   # Coluna A/B
        c_serv = df_m.columns[9]   # Coluna J (Descrição)
        c_unid = next((c for c in df_m.columns if 'UNID' in str(c).upper()), df_m.columns[10])
        c_precu = next((c for c in df_m.columns if 'UNIT' in str(c).upper()), df_m.columns[11])
        c_qtd_orc = next((c for c in df_m.columns if 'CONTRATADA' in str(c).upper() or 'QTD. ORC' in str(c).upper()), df_m.columns[12])
        
        # Criamos o DataFrame base
        resultado = df_m[[c_cod, c_serv, c_unid, c_precu, c_qtd_orc]].copy()
        resultado.columns = ['COD', 'SERVICO', 'UNID', 'PRECO_UNIT', 'QTD_ORC']
        
        # --- SOLUÇÃO PARA DUPLICIDADE ---
        # Usamos o índice da linha como parte da chave. Assim, a "Pavimentação" da linha 10 
        # nunca será confundida com a "Pavimentação" da linha 80 (outra unidade construtiva).
        resultado['ORDEM_ORIGINAL'] = range(len(resultado))
        resultado['CHAVE_JOIN'] = resultado['ORDEM_ORIGINAL'].astype(str) + "_" + resultado['COD'].astype(str).str.strip()

    except Exception as e:
        st.error(f"Erro ao montar esqueleto: {e}")
        st.stop()

    # --- 2. INTEGRAÇÃO DOS VALORES (Loop por cada arquivo enviado) ---
    for item in processados:
        try:
            eng = 'xlrd' if item['file'].name.endswith('.xls') else 'openpyxl'
            df_bm = pd.read_excel(item['file'], skiprows=25, engine=eng)
            label = item['label']
            
            # Criamos a mesma chave baseada na posição exata da linha na planilha
            df_bm['CHAVE_JOIN'] = df_bm.index.astype(str) + "_" + df_bm.iloc[:, 0].astype(str).str.strip()
            
            # Coleta de dados de Medição (Coluna 16) e Reajuste (Coluna 18)
            med_dados = pd.DataFrame()
            med_dados['CHAVE_JOIN'] = df_bm['CHAVE_JOIN']
            med_dados[f'VALOR_{label}'] = pd.to_numeric(df_bm.iloc[:, 16], errors='coerce').fillna(0)
            med_dados[f'REAJ_{label}'] = pd.to_numeric(df_bm.iloc[:, 18], errors='coerce').fillna(0)
            
            # Unimos ao resultado mestre usando a chave posicional
            resultado = pd.merge(resultado, med_dados, on='CHAVE_JOIN', how='left')
        except Exception as e:
            st.warning(f"Aviso: Não foi possível ler dados de {item['label']}. Erro: {e}")

    # --- 3. CONSOLIDAÇÃO FINAL ---
    resultado = resultado.fillna(0)
    # Limpeza de strings para visualização
    for col in ['COD', 'SERVICO', 'UNID']:
        resultado[col] = resultado[col].astype(str).replace(['nan', '0', '0.0', 'None'], '')

    # Identificamos as colunas de valores para somar o acumulado
    c_vals = [c for c in resultado.columns if 'VALOR_BM' in c]
    c_reajs = [c for c in resultado.columns if 'REAJ_BM' in c]

    resultado['VALOR_ACUMULADO'] = resultado[c_vals].sum(axis=1)
    resultado['REAJUSTE_ACUMULADO'] = resultado[c_reajs].sum(axis=1)
    resultado['TOTAL_GERAL'] = resultado['VALOR_ACUMULADO'] + resultado['REAJUSTE_ACUMULADO']

    # --- CÁLCULO DO TOTAL GERAL (Apenas linhas que são serviços reais) ---
    # Filtramos por quem tem 'UNID' preenchido para não somar títulos e evitar erros de R$ 44mi
    df_servicos = resultado[resultado['UNID'].astype(str).str.strip() != ""].copy()
    total_pi = df_servicos['VALOR_ACUMULADO'].sum()
    total_reaj = df_servicos['REAJUSTE_ACUMULADO'].sum()
    total_global = total_pi + total_reaj

    # Criamos uma linha extra de Total para aparecer no fim da tabela
    linha_total = pd.Series(dtype='object')
    linha_total['SERVICO'] = ">>> TOTAL ACUMULADO CALCULADO (SOMA DE ITENS COM UNIDADE)"
    linha_total['VALOR_ACUMULADO'] = total_pi
    linha_total['REAJUSTE_ACUMULADO'] = total_reaj
    linha_total['TOTAL_GERAL'] = total_global

    # Dataframe final para o Streamlit
    df_exibicao = pd.concat([resultado, linha_total.to_frame().T], ignore_index=True)
    df_exibicao = df_exibicao.drop(columns=['CHAVE_JOIN', 'ORDEM_ORIGINAL']).fillna(0)

    # --- EXIBIÇÃO: HISTÓRICO ---
    st.subheader(f"✅ Histórico Consolidado ({len(processados)} Medições)")
    format_dict = {col: formatar_br for col in df_exibicao.select_dtypes(include=['number']).columns}

    # Função para colorir títulos e a linha de total
    def destacar_linhas(row):
        if "TOTAL ACUMULADO" in str(row['SERVICO']):
            return ['background-color: #002b36; color: white; font-weight: bold'] * len(row)
        try:
            p_unit = float(row['PRECO_UNIT']) if row['PRECO_UNIT'] != "" else 0
            if p_unit == 0:
                return ['background-color: #f0f2f6; font-weight: bold; color: #1f77b4'] * len(row)
        except: pass
        return [''] * len(row)

    st.dataframe(
        df_exibicao.style.apply(destarcar_linhas if 'destarcar_linhas' in locals() else destacar_linhas, axis=1).format(format_dict), 
        use_container_width=True
    )

    # --- EXIBIÇÃO: CURVA ABC ---
    st.divider()
    st.subheader("📈 Curva ABC (Baseada no Total de Serviços)")
    # ABC usa apenas serviços com valor > 0
    abc = df_servicos[df_servicos['TOTAL_GERAL'] > 0.01].sort_values(by='TOTAL_GERAL', ascending=False)
    
    if not abc.empty:
        abc['%_SIMPLES'] = (abc['TOTAL_GERAL'] / total_global) * 100
        abc['%_ACUMULADO'] = abc['%_SIMPLES'].cumsum()
        abc['CLASSE'] = abc['%_ACUMULADO'].apply(lambda x: 'A' if x <= 80.01 else ('B' if x <= 95.01 else 'C'))

        # Cartões de Resumo
        c1, c2, c3 = st.columns(3)
        c1.metric("Soma PI", f"R$ {formatar_br(total_pi)}")
        c2.metric("Soma Reajuste", f"R$ {formatar_br(total_reaj)}")
        c3.metric("Total Global", f"R$ {formatar_br(total_global)}")

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

    # --- DOWNLOAD DO EXCEL ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_exibicao.to_excel(writer, sheet_name='Historico_Consolidado', index=False)
        if not abc.empty:
            abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
    
    st.sidebar.divider()
    st.sidebar.download_button(
        label="📥 Baixar Relatório Consolidado",
        data=output.getvalue(),
        file_name="consolidado_goinfra_abc.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Relatório Final (Excel)", output.getvalue(), "relatorio_goinfra_limpo.xlsx")
