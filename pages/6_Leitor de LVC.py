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
st.set_page_config(page_title="Leitor de LVC - Auditoria", layout="wide")

def get_cells_from_table(image):
    """
    Detecta a estrutura da tabela e extrai as células individualmente.
    Usa uma abordagem mais robusta para imagens com ruído ou variações.
    """
    # Converter para OpenCV
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Binarização adaptativa para lidar com sombras e variações de iluminação
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    
    # Definir tamanho dos kernels para detectar linhas
    # Usamos uma fração da largura/altura para sermos dinâmicos
    height, width = thresh.shape
    horizontal_size = width // 30
    vertical_size = height // 30
    
    # Detectar linhas horizontais
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))
    horizontal_lines = cv2.erode(thresh, hor_kernel, iterations=1)
    horizontal_lines = cv2.dilate(horizontal_lines, hor_kernel, iterations=3)
    
    # Detectar linhas verticais
    ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_size))
    vertical_lines = cv2.erode(thresh, ver_kernel, iterations=1)
    vertical_lines = cv2.dilate(vertical_lines, ver_kernel, iterations=3)
    
    # Máscara da tabela
    table_mask = cv2.add(horizontal_lines, vertical_lines)
    
    # Encontrar contornos
    contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filtrar contornos que parecem ser a tabela principal
    if not contours:
        return gray, []

    # Pegar o maior contorno (provavelmente a borda externa da tabela)
    table_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(table_contour)
    
    # Agora encontramos as células dentro dessa região
    table_roi = table_mask[y:y+h, x:x+w]
    inner_contours, _ = cv2.findContours(table_roi, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cells = []
    for c in inner_contours:
        cx, cy, cw, ch = cv2.boundingRect(c)
        # Filtro de tamanho para evitar ruídos e a própria tabela externa
        if 20 < cw < w*0.9 and 15 < ch < h*0.1:
            # Ajustar coordenadas para a imagem original
            cells.append((x + cx, y + cy, cw, ch))
            
    # Ordenar células: Primeiro por Y (linha) e depois por X (coluna)
    # Usamos uma tolerância de pixels para agrupar na mesma linha
    cells = sorted(cells, key=lambda b: (b[1] // 10, b[0]))
    
    return gray, cells

def analyze_cell(gray_img, rect, is_checkbox=False):
    """
    Analisa o conteúdo de uma célula baseada nas coordenadas.
    """
    x, y, w, h = rect
    cell_roi = gray_img[y:y+h, x:x+w]
    
    # Margem interna
    margin = 3
    if h > 2*margin and w > 2*margin:
        cell_roi = cell_roi[margin:-margin, margin:-margin]
    
    if is_checkbox:
        # Threshold para detectar caneta (marcas escuras)
        _, binary = cv2.threshold(cell_roi, 150, 255, cv2.THRESH_BINARY_INV)
        total_pixels = binary.size
        black_pixels = cv2.countNonZero(binary)
        density = black_pixels / total_pixels
        return density > 0.05  # 5% de preenchimento já indica marcação
    else:
        # OCR para texto
        config = '--psm 6'
        text = pytesseract.image_to_string(cell_roi, config=config, lang='por').strip()
        # Limpar caracteres comuns que o OCR confunde com lixo em células pequenas
        text = text.replace('|', '').replace('_', '').strip()
        return text

def process_lvc_sheet(uploaded_file):
    """
    Processa a ficha identificando a estrutura de colunas dinamicamente.
    """
    images = []
    if uploaded_file.type == "application/pdf":
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for img in images:
        gray, cells = get_cells_from_table(img)
        
        if not cells:
            continue

        # Tentar agrupar células em linhas baseando-se no Y
        rows = []
        if cells:
            current_row = [cells[0]]
            for i in range(1, len(cells)):
                # Se a diferença de Y for pequena, pertence à mesma linha
                if abs(cells[i][1] - current_row[-1][1]) < 15:
                    current_row.append(cells[i])
                else:
                    rows.append(current_row)
                    current_row = [cells[i]]
            rows.append(current_row)

        for r in rows:
            # Uma linha válida de LVC tem pelo menos os KMs e colunas de marcação
            # No modelo enviado, temos KM, KM, P, A, S, E, D, OBS...
            if len(r) < 5: 
                continue

            # Mapeamento simplificado por posição na linha
            # 0: KM inicial, 1: KM final, 2: P, 3: A, 4: S/E, 5: D, 6: Obs
            try:
                km_ini = analyze_cell(gray, r[0])
                km_fim = analyze_cell(gray, r[1])
                
                # Só processa se o primeiro KM for um número ou algo parecido
                if any(char.isdigit() for char in km_ini) or not km_ini:
                    row_data = {
                        "km_ini": km_ini,
                        "km_fim": km_fim,
                        "P": analyze_cell(gray, r[2], True) if len(r) > 2 else False,
                        "A": analyze_cell(gray, r[3], True) if len(r) > 3 else False,
                        "S": analyze_cell(gray, r[4], True) if len(r) > 4 else False,
                        "E": False, # Tratado junto com S na maioria das fichas
                        "D": analyze_cell(gray, r[5], True) if len(r) > 5 else False,
                        "observacoes": analyze_cell(gray, r[6]) if len(r) > 6 else ""
                    }
                    all_data.append(row_data)
            except:
                continue

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

# --- Interface ---
st.title("🚜 Leitor de Fichas LVC")
st.markdown("Analise de tabelas com detecção de marcações manuscritas.")

uploaded_file = st.file_uploader("Upload da Ficha", type=['pdf', 'png', 'jpg'])

if uploaded_file:
    if st.button("Processar Ficha", type="primary"):
        with st.spinner("Analisando estrutura da imagem..."):
            try:
                data = process_lvc_sheet(uploaded_file)
                
                if data:
                    st.success(f"Sucesso! {len(data)} linhas identificadas.")
                    df = pd.DataFrame(data)
                    
                    # Formatação visual para o Streamlit
                    view_df = df.copy()
                    for col in ["P", "A", "S", "E", "D"]:
                        view_df[col] = view_df[col].apply(lambda x: "✔️" if x else "")
                    
                    st.dataframe(view_df, use_container_width=True)
                    
                    xlsx = build_excel(data)
                    st.download_button(
                        "📥 Baixar Planilha Excel",
                        data=xlsx,
                        file_name=f"LVC_Processada.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Nenhuma linha de dados foi detectada. Tente uma imagem com maior contraste ou menos inclinação.")
                    
            except Exception as e:
                st.error(f"Erro no processamento: {e}")
                st.info("Dica: Verifique se o arquivo está nítido e as linhas da tabela estão visíveis.")
