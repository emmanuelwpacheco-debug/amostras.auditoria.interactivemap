import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Consolidação de medições e Curva ABC", layout="wide")
st.title("📊 Consolidação de Medições e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)", 
    type=['xls', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    # Lista para armazenar os dados de cada medição de forma organizada
    lista_consolidada = []
    
    for file in uploaded_files:
        try:
            # Lendo a planilha (ajustado para o padrão de cabeçalho da imagem)
            df = pd.read_excel(file, skiprows=25)
            
            # Limpeza inicial de colunas fantasmas e nomes
            df.columns = [str(c).strip() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('Unnamed|nan', case=False)]
            
            # Identificando as colunas principais (ajuste conforme a planilha)
            # Geralmente: 0:Código, 1:Serviço, 2:Unidade, 3:Preço Unitário
            col_cod = df.columns[0]
            col_serv = df.columns[1]
            col_unit = df.columns[4] # Valor Unitário
            
            # Pegando a coluna de 'Quantidade da Medição' (ajustar índice se necessário)
            # Na imagem padrão GOINFRA, costuma ser a coluna 'Da medição' sob 'Quantidades'
            col_qtd_med = [c for c in df.columns if 'medição' in c.lower() and 'valor' not in c.lower()]
            col_val_med = [c for c in df.columns if 'medição' in c.lower() and 'valor' in c.lower()]
            
            if col_qtd_med and col_val_med:
                # Criando um DataFrame simplificado para esta medição específica
                nome_med = file.name.replace('.xls', '').replace('.xlsx', '')
                
                temp = df[[col_cod, col_serv, col_unit, col_qtd_med[0], col_val_med[0]]].copy()
                temp.columns = ['Código', 'Serviço', 'Preço Unitário', f'Qtd_{nome_med}', f'Valor_{nome_med}']
                
                # Convertendo para número
                temp[f'Qtd_{nome_med}'] = pd.to_numeric(temp[f'Qtd_{nome_med}'], errors='coerce').fillna(0)
                temp[f'Valor_{nome_med}'] = pd.to_numeric(temp[f'Valor_{nome_med}'], errors='coerce').fillna(0)
                temp['Preço Unitário'] = pd.to_numeric(temp['Preço Unitário'], errors='coerce').fillna(0)
                
                # Remove linhas sem código (títulos de seções)
                temp = temp.dropna(subset=['Código'])
                lista_consolidada.append(temp)
                
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if lista_consolidada:
        # Fazendo o Merge de todas as medições pelo Código e Serviço
        df_final = lista_consolidada[0]
        for i in range(1, len(lista_consolidada)):
            df_final = pd.merge(
                df_final, 
                lista_consolidada[i], 
                on=['Código', 'Serviço', 'Preço Unitário'], 
                how='outer'
            ).fillna(0)

        # Calculando os Totais Acumulados
        colunas_qtd = [c for c in df_final.columns if 'Qtd_' in c]
        colunas_val = [c for c in df_final.columns if 'Valor_' in c]
        
        df_final['Qtd Acumulada'] = df_final[colunas_qtd].sum(axis=1)
        df_final['Valor Acumulado'] = df_final[colunas_val].sum(axis=1)

        # --- ABA 1: CONSOLIDAÇÃO DETALHADA ---
        st.subheader("📋 Consolidação por Medição (Vista Sequencial)")
        st.dataframe(df_final, use_container_width=True)

        # --- ABA 2: CURVA ABC ---
        if st.button("📈 Gerar Curva ABC do Acumulado"):
            abc = df_final[df_final['Valor Acumulado'] > 0].copy()
            abc = abc[['Código', 'Serviço', 'Preço Unitário', 'Qtd Acumulada', 'Valor Acumulado']]
            abc = abc.sort_values(by='Valor Acumulado', ascending=False)
            
            total_geral = abc['Valor Acumulado'].sum()
            abc['% Simples'] = (abc['Valor Acumulado'] / total_geral) * 100
            abc['% Acumulada'] = abc['% Simples'].cumsum()
            abc['Classe'] = abc['% Acumulada'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))
            
            st.divider()
            st.subheader("🏆 Classificação ABC (Total Acumulado)")
            st.metric("Investimento Total Consolidado", f"R$ {total_geral:,.2f}")
            st.dataframe(abc.style.format({'Preço Unitário': '{:.2f}', 'Valor Acumulado': '{:.2f}', '% Acumulada': '{:.2f}%'}), use_container_width=True)

            # Exportação
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, sheet_name='Consolidado_Sequencial', index=False)
                abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
            
            st.download_button(
                "📥 Baixar Relatório Completo (Excel)", 
                output.getvalue(), 
                "consolidacao_fiscalizacao_GO.xlsx"
            )
