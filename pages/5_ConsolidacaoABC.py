import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidação e Curva ABC", layout="wide")

st.title("📊 Consolidação de Medições (Padrão GOINFRA)")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (Excel)", 
    type=['xlsx', 'xls'], 
    accept_multiple_files=True
)

if uploaded_files:
    dfs_processados = []
    
    for file in uploaded_files:
        try:
            # Pula as 25 linhas administrativas. A 26 é o cabeçalho.
            df = pd.read_excel(file, skiprows=25)
            
            # Limpa os nomes das colunas
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            # FILTRO DE SEGURANÇA: Só mantém linhas onde o 'CÓDIGO' existe
            # Isso remove as células mescladas de títulos de grupos (ex: '1. SERVIÇOS INICIAIS')
            col_codigo_nome = df.columns[0]
            df = df.dropna(subset=[col_codigo_nome])
            
            # Adiciona o nome do arquivo para controle
            df['FONTE_MEDICAO'] = file.name
            dfs_processados.append(df)
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")
    
    if dfs_processados:
        df_total = pd.concat(dfs_processados, ignore_index=True)
        cols = df_total.columns.tolist()

        st.subheader("⚙️ Verifique o Mapeamento")
        c1, c2, c3, c4 = st.columns(4)
        
        # Tentativa de pré-seleção baseada em palavras-chave
        def auto_detect(options):
            for i, c in enumerate(cols):
                if any(opt in c for opt in options): return i
            return 0

        with c1: col_id = st.selectbox("Cód. Serviço", cols, index=auto_detect(['CÓDIGO', 'ITEM']))
        with c2: col_desc = st.selectbox("Descrição", cols, index=auto_detect(['SERVIÇO', 'DESCRIÇÃO']))
        with c3: col_qtd = st.selectbox("Qtd Medição", cols, index=auto_detect(['DA MEDIÇÃO', 'QTD']))
        with c4: col_uni = st.selectbox("Preço Unitário", cols, index=auto_detect(['UNITÁRIO', 'VALOR U']))

        if st.button("📈 Gerar Relatório Consolidado"):
            # Limpeza Numérica
            df_total[col_qtd] = pd.to_numeric(df_total[col_qtd], errors='coerce').fillna(0)
            df_total[col_uni] = pd.to_numeric(df_total[col_uni], errors='coerce').fillna(0)
            
            # Consolidação
            consolidado = df_total.groupby([col_id, col_desc, col_uni]).agg({
                col_qtd: 'sum'
            }).reset_index()
            
            consolidado['VALOR_TOTAL'] = consolidado[col_qtd] * consolidado[col_uni]
            
            # Ranking ABC
            abc = consolidado[consolidado['VALOR_TOTAL'] > 0].sort_values(by='VALOR_TOTAL', ascending=False).copy()
            total_geral = abc['VALOR_TOTAL'].sum()
            abc['%_SIMPLES'] = (abc['VALOR_TOTAL'] / total_geral) * 100
            abc['%_ACUMULADA'] = abc['%_SIMPLES'].cumsum()
            abc['CLASSE'] = abc['%_ACUMULADA'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))

            # Dashboard
            st.divider()
            m1, m2 = st.columns(2)
            m1.metric("Total Acumulado", f"R$ {total_geral:,.2f}")
            m2.metric("Itens Críticos (Classe A)", len(abc[abc['CLASSE'] == 'A']))

            st.dataframe(abc, use_container_width=True)

            # Exportação em duas abas
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
                df_total.to_excel(writer, sheet_name='Itens_Detalhado', index=False)
            
            st.download_button("📥 Baixar Excel Consolidado", output.getvalue(), "Consolidado_ABC.xlsx")
