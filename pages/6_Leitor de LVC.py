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
    
    # Binarização para destacar as linhas da tabela
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
    
    # Máscara de interseções (os "cantos" ou a própria grade)
    grid = cv2.add(hor, ver)
    
    # Encontrar contornos de cada célula individualmente
    contours, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cells = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Filtros para ignorar a página inteira ou ruídos minúsculos
        if 20 < w < (thresh.shape[1] * 0.9) and 15 < h < 150:
            cells.append((x, y, w, h))
            
    # Ordenar células: Primeiro por Y (linha) e depois por X (coluna)
    # Usamos uma tolerância maior (h/2) para agrupar na mesma linha
    if not cells:
        return []
    
    cells = sorted(cells, key=lambda b: (b[1], b[0]))
    
    # Agrupar em linhas reais
    rows = []
    if cells:
        current_row = [cells[0]]
        for i in range(1, len(cells)):
            # Se a diferença de Y for menor que metade da altura da célula anterior, é a mesma linha
            if abs(cells[i][1] - current_row[-1][1]) < (current_row[-1][3] / 2):
                current_row.append(cells[i])
            else:
                rows.append(sorted(current_row, key=lambda b: b[0]))
                current_row = [cells[i]]
        rows.append(sorted(current_row, key=lambda b: b[0]))
        
    return rows

def analyze_cell_content(gray_img, rect, is_checkbox=False):
    """Extrai texto ou detecta marcação manual em uma célula."""
    x, y, w, h = rect
    # Cortar margem para evitar a linha preta da tabela
    pad_w = int(w * 0.1)
    pad_h = int(h * 0.15)
    cell_roi = gray_img[y+pad_h:y+h-pad_h, x+pad_w:x+w-pad_w]
    
    if cell_roi.size == 0:
        return False if is_checkbox else ""

    if is_checkbox:
        _, binary = cv2.threshold(cell_roi, 170, 255, cv2.THRESH_BINARY_INV)
        density = cv2.countNonZero(binary) / binary.size
        return density > 0.05
    else:
        text = pytesseract.image_to_string(cell_roi, config='--psm 6').strip()
        for char in "|_[]—": text = text.replace(char, "")
        return text

def process_dynamic_sheet(uploaded_file):
    """Processa múltiplas páginas e qualquer quantidade de linhas."""
    images = []
    if uploaded_file.type == "application/pdf":
        # Converter PDF completo para lista de imagens
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for page_num, img in enumerate(images):
        gray, thresh = preprocess_for_extraction(img)
        row_structures = get_table_cells(thresh, gray)
        
        for r_cells in row_structures:
            # Uma linha de dados legítima deve ter entre 6 a 10 colunas
            # Ignora linhas de cabeçalho (que costumam ter textos longos ou poucas células grandes)
            if len(r_cells) < 6:
                continue
                
            # Extração baseada na ordem das colunas da esquerda para a direita
            # KM_INI, KM_FIM, P, A, S, E, D, OBS...
            km_ini = analyze_cell_content(gray, r_cells[0])
            
            # Validação simples: se não houver número ou texto no KM, pode ser ruído, 
            # mas vamos manter se houver marcação nas patologias
            km_fim = analyze_cell_content(gray, r_cells[1])
            
            # Nas colunas centrais, verificamos marcação
            p = analyze_cell_content(gray, r_cells[2], True)
            a = analyze_cell_content(gray, r_cells[3], True)
            s = analyze_cell_content(gray, r_cells[4], True)
            
            # A coluna de observações costuma ser a penúltima ou última maior
            obs_cell = r_cells[min(len(r_cells)-1, 7)]
            obs = analyze_cell_content(gray, obs_cell)

            all_data.append({
                "página": page_num + 1,
                "km_ini": km_ini,
                "km_fim": km_fim,
                "P": p,
                "A": a,
                "S": s,
                "E": analyze_cell_content(gray, r_cells[5], True) if len(r_cells) > 5 else False,
                "D": analyze_cell_content(gray, r_cells[6], True) if len(r_cells) > 6 else False,
                "observacoes": obs
            })

    return all_data

def build_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "LVC Consolidado"
    
    headers = ["PÁGINA", "KM INICIAL", "KM FINAL", "P", "A", "S", "E", "D", "OBSERVAÇÕES"]
    ws.append(headers)
    
    # Estilos
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
st.title("🚜 Leitor de LVC Universal")
st.markdown("""
Este leitor processa **qualquer número de páginas** e detecta as linhas da tabela dinamicamente.
Ideal para fichas longas ou com estruturas variáveis.
""")

uploaded_file = st.file_uploader("Upload da Ficha (PDF multi-página ou Imagem)", type=['pdf', 'png', 'jpg'])

if uploaded_file:
    if st.button("Iniciar Extração Completa", type="primary"):
        with st.spinner("Analisando documentos e extraindo dados..."):
            try:
                data = process_dynamic_sheet(uploaded_file)
                
                if data:
                    st.success(f"Extração concluída! {len(data)} linhas encontradas em {data[-1]['página']} página(s).")
                    
                    df = pd.DataFrame(data)
                    # Exibir amostra dos dados
                    st.dataframe(df, use_container_width=True)
                    
                    excel_data = build_excel(data)
                    st.download_button(
                        label="📥 Descarregar Excel Completo",
                        data=excel_data,
                        file_name=f"LVC_Extraido_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Nenhuma tabela de dados reconhecida. Verifique se as linhas da ficha estão bem visíveis.")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")
