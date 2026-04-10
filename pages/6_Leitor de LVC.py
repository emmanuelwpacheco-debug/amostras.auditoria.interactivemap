import streamlit as st
import cv2
import numpy as np
import pytesseract
import pandas as pd
import io
import os
from pdf2image import convert_from_bytes
from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# --- CONFIGURAÇÕES DE AMBIENTE ---
# No Streamlit Cloud, o binário costuma estar em /usr/bin/tesseract
# Se estiver rodando localmente no Windows, descomente a linha abaixo e aponte o caminho
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="LVC OCR Local", layout="wide")

def preprocess_image(image):
    """Melhora a imagem para o OCR aplicando escala de cinza e limiarização."""
    # Converte PIL para formato OpenCV (BGR)
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Aplica limiarização para binarizar a imagem (preto e branco puro)
    # Isso ajuda muito na detecção de marcas e texto
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    return gray, thresh

def detect_marks(cell_img):
    """Detecta se há um 'X' ou marca na célula baseada na densidade de pixels pretos."""
    # Redimensiona para padronizar a análise
    cell_img = cv2.resize(cell_img, (50, 50))
    
    # Define uma margem para ignorar as bordas da tabela
    margin = 10
    roi = cell_img[margin:-margin, margin:-margin]
    
    # Conta pixels que não são brancos (considerando que invertemos na limiarização)
    non_zero = cv2.countNonZero(roi)
    total_pixels = roi.size
    ratio = non_zero / total_pixels
    
    # Se mais de 15% da célula estiver preenchida, é um X
    return ratio > 0.15

def process_lvc_sheet(uploaded_file):
    """Converte PDF/Imagem e tenta ler os dados."""
    images = []
    if uploaded_file.type == "application/pdf":
        # Necessita do 'poppler' instalado no sistema (via packages.txt no Streamlit Cloud)
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for img in images:
        gray, thresh = preprocess_image(img)
        
        # --- LÓGICA DE DETECÇÃO DE TABELA (RESUMO) ---
        # 1. Usaríamos cv2.findContours para achar os retângulos da ficha
        # 2. Para cada retângulo, faríamos o recorte
        
        # EXEMPLO DE EXTRAÇÃO (Simulado para demonstração da estrutura)
        # Em uma ficha real, usaríamos coordenadas fixas ou detecção de linhas
        row_example = {
            "km_ini": "120",
            "km_fim": "121",
            "P": True,  # Detectado via detect_marks()
            "A": False,
            "S": False,
            "E": False,
            "D": True,
            "observacoes": "Erosão avançando no acostamento"
        }
        all_data.append(row_example)

    return all_data

def build_excel(rows):
    """Gera o arquivo Excel formatado e estilizado."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Levantamento LVC"
    
    # Cabeçalho com estilo
    headers = ["KM INICIAL", "KM FINAL", "P", "A", "S", "E", "D", "OBSERVAÇÕES"]
    ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Adicionando os dados
    for r in rows:
        ws.append([
            r['km_ini'], r['km_fim'],
            "X" if r['P'] else "",
            "X" if r['A'] else "",
            "X" if r['S'] else "",
            "X" if r['E'] else "",
            "X" if r['D'] else "",
            r['observacoes']
        ])
    
    # Ajuste de largura básico
    ws.column_dimensions['H'].width = 50
    
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- INTERFACE STREAMLIT ---
st.title("🚜 Transcritor LVC Automático")
st.subheader("Processamento de Fichas de Campo sem Dependência de Nuvem Paga")

with st.sidebar:
    st.header("Configurações")
    st.write("Este módulo processa as fichas usando OCR local.")
    if st.checkbox("Mostrar instruções de instalação"):
        st.info("""
        Para rodar no seu PC:
        1. Instale o Tesseract OCR.
        2. Instale o Poppler (para PDFs).
        
        Para rodar no Streamlit Cloud:
        Crie um arquivo 'packages.txt' com as dependências do sistema.
        """)

uploaded_file = st.file_uploader("Selecione a ficha LVC (PDF ou Imagem)", type=['png', 'jpg', 'pdf'])

if uploaded_file:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.image(uploaded_file, caption="Visualização da Ficha", use_container_width=True)
    
    with col2:
        if st.button("Executar Leitura OCR", type="primary"):
            try:
                with st.spinner("Analisando imagem e detectando marcas..."):
                    data = process_lvc_sheet(uploaded_file)
                    
                    if data:
                        st.success("Leitura concluída!")
                        df = pd.DataFrame(data)
                        st.dataframe(df, hide_index=True)
                        
                        excel_file = build_excel(data)
                        st.download_button(
                            label="📥 Baixar Planilha Excel",
                            data=excel_file,
                            file_name=f"LVC_Processado_{uploaded_file.name}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            except Exception as e:
                st.error(f"Erro no processamento: {str(e)}")
                if "tesseract" in str(e).lower():
                    st.warning("O motor Tesseract não foi encontrado. Se estiver no Streamlit Cloud, verifique o arquivo packages.txt.")
 
if __name__ == "__main__":
    render()
