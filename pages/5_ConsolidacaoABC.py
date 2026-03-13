import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidador de Histórico", layout="wide")
st.title("📑 Consolidador de Histórico Acumulado e Aditivos")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (ordene pela data de ocorrência)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    # Dicionário para armazenar os dados de cada Boletim de Medição (BM)
    bms = {}
    colunas_base = ['CÓDIGO', 'SERVIÇO', 'UNIDADE', 'PREÇO UNITÁRIO', 'QUANTIDADE TOTAL']
    
    for file in uploaded_files:
        try:
            # Leitura a partir da linha 26 (padrão GOINFRA)
            df = pd.read_excel(file, skiprows=25)
            
            # Limpeza de colunas
            df.columns = [str(c).strip().upper() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('UNNAMED|NAN', case=False)]
            
            # Identificação das colunas críticas
            # Adaptamos para buscar nomes que contenham as palavras-chave
            def buscar_col(termos):
                for c in df.columns:
                    if any(t in c for t in termos): return c
                return None

            c_cod = buscar_col(['CÓDIGO', 'ITEM'])
            c_serv = buscar_col(['SERVIÇO', 'DESCRIÇÃO'])
            c_unid = buscar_col(['UNIDADE', 'UNID'])
            c_pre = buscar_col(['PREÇO UNITÁRIO', 'VALOR UNIT'])
            c_qtd_orc = buscar_col(['QUANTIDADE', 'QTD. ORC'])
            
            # Colunas da Medição Atual
            c_qtd_bm = buscar_col(['DA MEDIÇÃO', 'QTD. MED'])
            c_val_bm = buscar_col(['VALOR DA MED', 'VALOR MED'])
            c_k0 = buscar_col(['K0', 'FATOR'])
            c_reaj = buscar_col(['REAJUSTE'])

            # Nome simplificado do BM baseado no arquivo
            nome_bm = file.name.replace('.xls', '').replace('.xlsx', '')

            # Seleção e renomeação para padronização
            df_bm = df[[c_cod, c_serv, c_unid, c_pre, c_qtd_orc, c_qtd_bm, c_val_bm, c_k0, c_reaj]].copy()
            df_bm.columns = ['CÓDIGO', 'SERVIÇO', 'UNIDADE', 'PREÇO UNITÁRIO', 'QTD_ORC', 
                             f'QTD_{nome_bm}', f'VALOR_{nome_bm}', f'K0_{nome_bm}', f'REAJ_{nome_bm}']
            
            bms[nome_bm] = df_bm
            
        except Exception as e:
            st.error(f"Erro no arquivo {file.name}: {e}")

    if bms:
        # 1. Criar a Lista Mestre de Serviços (Unificando Aditivos)
        # Concatenamos todos os códigos e serviços encontrados em todos os arquivos
        lista_mestre = pd.concat([df[['CÓDIGO', 'SERVIÇO', 'UNIDADE', 'PREÇO UNITÁRIO', 'QTD_ORC']] for df in bms.values()])
        # Remove duplicatas mantendo a última definição (útil se o preço mudar por aditivo)
        lista_mestre = lista_mestre.drop_duplicates(subset=['CÓDIGO', 'SERVIÇO'], keep='last')

        # 2. Unir cada BM à Lista Mestre (Merge)
        df_final = lista_mestre
        for nome_bm, df_bm in bms.items():
            # Pegamos apenas as colunas específicas daquela medição
            colunas_medicao = ['CÓDIGO', 'SERVIÇO', f'QTD_{nome_bm}', f'VALOR_{nome_bm}', f'K0_{nome_bm}', f'REAJ_{nome_bm}']
            df_final = pd.merge(df_final, df_bm[colunas_medicao], on=['CÓDIGO', 'SERVIÇO'], how='left')

        # 3. Cálculos de Acumulado
        col_qtds = [c for c in df_final.columns if 'QTD_' in c and 'ORC' not in c]
        col_vals = [c for c in df_final.columns if 'VALOR_' in c]
        col_reaj = [c for c in df_final.columns if 'REAJ_' in c]

        df_final = df_final.fillna(0) # Transforma vazios em 0 para somar
        
        df_final['QUANTIDADE ACUMULADA'] = df_final[col_qtds].sum(axis=1)
        df_final['VALOR ACUMULADO'] = df_final[col_vals].sum(axis=1)
        df_final['VALOR REAJUSTE ACUMULADO'] = df_final[col_reaj].sum(axis=1)

        # 4. Tratamento de Unidades Construtivas
        # Se Qtd, Unid e Preço são 0, é uma linha de grupo
        def marcar_grupo(row):
            if str(row['UNIDADE']) in ['0', 'nan', ''] and row['PREÇO UNITÁRIO'] == 0:
                return "📂 GRUPO"
            return "🔧 SERVIÇO"
        
        df_final['TIPO'] = df_final.apply(marcar_grupo, axis=1)

        # --- EXIBIÇÃO ---
        st.subheader("📊 Histórico Acumulado Consolidado")
        st.write("A tabela abaixo reflete todos os serviços, incluindo aditivos detectados.")
        
        # Estilização básica
        st.dataframe(df_final, use_container_width=True)

        # Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Historico_Acumulado')
        
        st.download_button(
            "📥 Baixar Histórico Completo", 
            output.getvalue(), 
            "historico_consolidado_obras.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
