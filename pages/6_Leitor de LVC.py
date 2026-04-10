import streamlit as st
import io
import re
import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Leitor de LVC - Auditoria", layout="wide")

def get_cells_from_table(image):
    """
    Detecta a estrutura da tabela e extrai as células individualmente.
    """
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Binarização para destacar as linhas da tabela
    thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    
    # Detectar linhas horizontais e verticais
    kernel_len = np.array(img_cv).shape[1] // 100
    ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_len))
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
    
    image_1 = cv2.erode(thresh, ver_kernel, iterations=3)
    vertical_lines = cv2.dilate(image_1, ver_kernel, iterations=3)
    
    image_2 = cv2.erode(thresh, hor_kernel, iterations=3)
    horizontal_lines = cv2.dilate(image_2, hor_kernel, iterations=3)
    
    # Combinar linhas para formar a grade
    table_segment = cv2.addWeighted(vertical_lines, 0.5, horizontal_lines, 0.5, 0.0)
    table_segment = cv2.threshold(table_segment, 0, 255, cv2.THRESH_BINARY)[1]
    
    # Encontrar contornos das células
    contours, _ = cv2.findContours(table_segment, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    # Organizar contornos por posição (Y, X)
    def get_contour_precedence(contour, cols):
        tolerance_factor = 10
        origin = cv2.boundingRect(contour)
        return ((origin[1] // tolerance_factor) * tolerance_factor) * cols + origin[0]

    # Filtrar apenas contornos que parecem células (evitar ruídos muito pequenos ou muito grandes)
    cells = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 20 < w < 1000 and 15 < h < 100:
            cells.append(c)
            
    # Ordenar células (cima para baixo, esquerda para direita)
    cells = sorted(cells, key=lambda c: get_contour_precedence(c, img_cv.shape[1]))
    
    return gray, cells

def analyze_cell(gray_img, contour, is_checkbox=False):
    """
    Analisa o conteúdo de uma célula específica.
    """
    x, y, w, h = cv2.boundingRect(contour)
    cell_roi = gray_img[y:y+h, x:x+w]
    
    # Margem para ignorar a borda da tabela
    margin = 5
    if h > 2*margin and w > 2*margin:
        cell_roi = cell_roi[margin:-margin, margin:-margin]
    
    if is_checkbox:
        # Para checkboxes, medimos a densidade de "tinta"
        thresh = cv2.threshold(cell_roi, 180, 255, cv2.THRESH_BINARY_INV)[1]
        non_zero = cv2.countNonZero(thresh)
        ratio = non_zero / float(w * h)
        return ratio > 0.1  # Se > 10% estiver preenchido, consideramos marcado
    else:
        # Para texto, usamos OCR
        text = pytesseract.image_to_string(cell_roi, config='--psm 6').strip()
        return text

def process_lvc_sheet(uploaded_file):
    """
    Processa a ficha mantendo a fidelidade de todas as linhas.
    """
    images = []
    if uploaded_file.type == "application/pdf":
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for img in images:
        gray, cells = get_cells_from_table(img)
        
        # O PDF enviado tem colunas: KM_INI, KM_FIM, P, A, S, E, D, OBS, PONTO, FOTO (aprox 10 colunas)
        # Vamos agrupar as células em linhas (geralmente 8 a 10 colunas por linha)
        num_cols = 10 
        rows_cells = [cells[i:i + num_cols] for i in range(0, len(cells), num_cols)]
        
        for r_cells in rows_cells:
            if len(r_cells) < 5: continue # Pula se não for uma linha completa
            
            # Extração baseada na posição da coluna na ficha
            km_ini = analyze_cell(gray, r_cells[0])
            km_fim = analyze_cell(gray, r_cells[1])
            
            # Se não houver KM, pode ser cabeçalho ou ruído, mas vamos manter se houver KM
            if not km_ini and not km_fim: continue

            row = {
                "km_ini": km_ini,
                "km_fim": km_fim,
                "P": analyze_cell(gray, r_cells[2], is_checkbox=True),
                "A": analyze_cell(gray, r_cells[3], is_checkbox=True),
                "S": analyze_cell(gray, r_cells[4], is_checkbox=True),
                "E": analyze_cell(gray, r_cells[4], is_checkbox=True), # Note: na ficha S e E as vezes dividem coluna
                "D": analyze_cell(gray, r_cells[5], is_checkbox=True),
                "observacoes": analyze_cell(gray, r_cells[6]) if len(r_cells) > 6 else ""
            }
            all_data.append(row)

    return all_data

def build_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "LVC Auditoria"
    
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                         top=Side(style='thin'), bottom=Side(style='thin'))

    headers = ["KM INICIAL", "KM FINAL", "P", "A", "S", "E", "D", "OBSERVAÇÕES"]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    for r_idx, r in enumerate(rows, 2):
        values = [r['km_ini'], r['km_fim'], 
                  "X" if r['P'] else "", "X" if r['A'] else "", 
                  "X" if r['S'] else "", "X" if r['E'] else "", 
                  "X" if r['D'] else "", r['observacoes']]
        
        for c_idx, val in enumerate(values, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.border = thin_border
            if c_idx <= 7: cell.alignment = center_align

    ws.column_dimensions['H'].width = 50
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- UI ---
st.title("🚜 Leitor de Fichas LVC (Fidelidade de Tabela)")
st.markdown("Esta versão analisa a **grade da tabela** para garantir que linhas em branco sejam preservadas.")

uploaded_file = st.file_uploader("Upload da Ficha (PDF ou Imagem)", type=['pdf', 'png', 'jpg'])

if uploaded_file:
    if st.button("Processar com Precisão de Tabela", type="primary"):
        with st.spinner("Mapeando colunas e detectando marcações..."):
            try:
                data = process_lvc_sheet(uploaded_file)
                st.success(f"Processamento finalizado. {len(data)} linhas detectadas.")
                
                df = pd.DataFrame(data)
                # Visualização amigável
                display_df = df.copy()
                for col in ["P", "A", "S", "E", "D"]:
                    display_df[col] = display_df[col].apply(lambda x: "✔️" if x else "")
                
                st.dataframe(display_df, use_container_width=True)
                
                excel_data = build_excel(data)
                st.download_button(
                    label="📥 Baixar Planilha Fiel à Ficha",
                    data=excel_data,
                    file_name=f"LVC_Fiel_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Erro ao mapear tabela: {e}")
                st.info("Dica: Certifique-se de que a ficha não está muito inclinada na foto.")
