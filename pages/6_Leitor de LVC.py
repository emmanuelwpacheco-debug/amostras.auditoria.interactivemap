import streamlit as st
import io
import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Leitor de LVC - Dinâmico", layout="wide")

def preprocess_for_extraction(image):
    """Prepara a imagem para detecção de linhas de grade."""
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Binarização adaptativa para destacar as linhas da tabela
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    return gray, thresh

def get_table_cells(thresh, gray):
    """Detecta as linhas da tabela e agrupa em células dinâmicas."""
    # Detectar linhas horizontais e verticais
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (thresh.shape[1] // 50, 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, thresh.shape[0] // 50))
    
    hor = cv2.dilate(cv2.erode(thresh, kernel_h), kernel_h, iterations=2)
    ver = cv2.dilate(cv2.erode(thresh, kernel_v), kernel_v, iterations=2)
    
    # Máscara de interseções
    grid = cv2.add(hor, ver)
    
    # Encontrar contornos de cada célula
    contours, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cells = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 20 < w < (thresh.shape[1] * 0.9) and 15 < h < 150:
            cells.append((x, y, w, h))
            
    if not cells:
        return []
    
    cells = sorted(cells, key=lambda b: (b[1], b[0]))
    
    # Agrupar em linhas
    rows = []
    current_row = [cells[0]]
    for i in range(1, len(cells)):
        if abs(cells[i][1] - current_row[-1][1]) < (current_row[-1][3] / 2):
            current_row.append(cells[i])
        else:
            rows.append(sorted(current_row, key=lambda b: b[0]))
            current_row = [cells[i]]
    rows.append(sorted(current_row, key=lambda b: b[0]))
        
    return rows

def analyze_cell_content(gray_img, rect, is_checkbox=False):
    """Extrai texto ou detecta marcação manual 'X' de forma mais precisa."""
    x, y, w, h = rect
    # Margem interna para ignorar bordas da célula
    pad_w = int(w * 0.15)
    pad_h = int(h * 0.15)
    cell_roi = gray_img[y+pad_h:y+h-pad_h, x+pad_w:x+w-pad_w]
    
    if cell_roi.size == 0:
        return False if is_checkbox else ""

    if is_checkbox:
        # Aumentar contraste local para destacar a caneta
        cell_roi = cv2.normalize(cell_roi, None, 0, 255, cv2.NORM_MINMAX)
        
        # Binarização inversa (caneta fica branca)
        _, binary = cv2.threshold(cell_roi, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Limpeza morfológica: Remove pequenos pontos que não são traços
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        # Se após a limpeza ainda houver uma quantidade significativa de pixels, 
        # é provável que seja um X ou marcação manual.
        non_zero = cv2.countNonZero(binary)
        density = non_zero / binary.size
        
        # Threshold de densidade ajustado para ser mais rigoroso contra ruído
        return density > 0.08
    else:
        text = pytesseract.image_to_string(cell_roi, config='--psm 6').strip()
        for char in "|_[]—": text = text.replace(char, "")
        return text

def process_dynamic_sheet(uploaded_file):
    """Processa múltiplas páginas e qualquer quantidade de linhas."""
    images = []
    if uploaded_file.type == "application/pdf":
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for page_num, img in enumerate(images):
        gray, thresh = preprocess_for_extraction(img)
        row_structures = get_table_cells(thresh, gray)
        
        for r_cells in row_structures:
            # Filtro para linhas de dados legítimas
            if len(r_cells) < 6:
                continue
                
            # Extração baseada na ordem das colunas
            # 0:KM, 1:KM_FIM (ou prox cel), 2:P, 3:A, 4:S, 5:E, 6:D...
            # Ajustado para lidar com o fato de que S e E as vezes são células separadas detectadas
            
            km_ini = analyze_cell_content(gray, r_cells[0])
            km_fim = analyze_cell_content(gray, r_cells[1])
            
            p = analyze_cell_content(gray, r_cells[2], True)
            a = analyze_cell_content(gray, r_cells[3], True)
            s = analyze_cell_content(gray, r_cells[4], True)
            
            # Tenta localizar a coluna de observações (normalmente a maior no final)
            obs = ""
            if len(r_cells) > 5:
                # Procurar a célula com maior largura entre as últimas
                last_cells = r_cells[5:]
                obs_cell = max(last_cells, key=lambda b: b[2])
                obs = analyze_cell_content(gray, obs_cell)

            all_data.append({
                "página": page_num + 1,
                "km_ini": km_ini,
                "km_fim": km_fim,
                "P": p,
                "A": a,
                "S": s,
                "E": analyze_cell_content(gray, r_cells[5], True) if len(r_cells) > 7 else False,
                "D": analyze_cell_content(gray, r_cells[6], True) if len(r_cells) > 8 else False,
                "observacoes": obs
            })

    return all_data

def build_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "LVC Consolidado"
    
    headers = ["PÁGINA", "KM INICIAL", "KM FINAL", "P", "A", "S", "E", "D", "OBSERVAÇÕES"]
    ws.append(headers)
    
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for r_idx, r in enumerate(rows, 2):
        data_row = [
            r['página'], r['km_ini'], r['km_fim'],
            "X" if r['P'] else "", "X" if r['A'] else "",
            "X" if r['S'] else "", "X" if r['E'] else "",
            "X" if r['D'] else "", r['observacoes']
        ]
        ws.append(data_row)

    ws.column_dimensions['I'].width = 50
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- Interface ---
st.title("🚜 Leitor de LVC Universal - Precisão 'X'")
st.markdown("""
Extração dinâmica otimizada para identificar marcações manuais (X) e ignorar ruídos.
""")

uploaded_file = st.file_uploader("Upload da Ficha (PDF ou Imagem)", type=['pdf', 'png', 'jpg'])

if uploaded_file:
    if st.button("Iniciar Extração Completa", type="primary"):
        with st.spinner("Analisando células e marcações..."):
            try:
                data = process_dynamic_sheet(uploaded_file)
                
                if data:
                    st.success(f"Extração concluída! {len(data)} linhas encontradas.")
                    st.dataframe(pd.DataFrame(data), use_container_width=True)
                    
                    excel_data = build_excel(data)
                    st.download_button(
                        label="📥 Descarregar Excel Completo",
                        data=excel_data,
                        file_name=f"LVC_Processada_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Nenhuma linha detectada. Verifique o contraste da imagem.")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")
