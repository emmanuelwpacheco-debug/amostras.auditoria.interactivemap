import streamlit as st
import cv2
import numpy as np
import pytesseract
import pandas as pd
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Título da página específica no menu do Streamlit
st.set_page_config(page_title="Leitor de LVC", layout="wide")

def preprocess_for_grid(image):
    """Prepara a imagem para detecção de linhas de tabela."""
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    remove_horiz = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horiz_kernel, iterations=2)
    
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    remove_vert = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vert_kernel, iterations=2)
    
    table_mask = remove_horiz + remove_vert
    return gray, thresh, table_mask

def process_lvc_sheet(uploaded_file):
    """Processa a ficha baseada no modelo enviado."""
    images = []
    if uploaded_file.type == "application/pdf":
        images = convert_from_bytes(uploaded_file.read())
    else:
        images = [Image.open(uploaded_file)]

    all_data = []

    for img in images:
        gray, _, _ = preprocess_for_grid(img)
        
        try:
            # Tenta usar português, se falhar vai para o padrão
            full_text = pytesseract.image_to_string(gray, lang='por')
        except:
            full_text = pytesseract.image_to_string(gray)
        
        lines = full_text.split('\n')
        for line in lines:
            # Busca padrões de KM (Início e Fim)
            match = re.search(r'(\d+)\s+.*?\s+(\d+)', line)
            if match:
                km_ini = match.group(1)
                km_fim = match.group(2)
                
                row = {
                    "km_ini": km_ini,
                    "km_fim": km_fim,
                    "P": any(x in line.upper() for x in ["X", "(P)", "PANELA"]),
                    "A": any(x in line.upper() for x in ["X", "☑", "(A)", "AFUND"]),
                    "S": "(S)" in line.upper(),
                    "E": "(E)" in line.upper(),
                    "D": "(D)" in line.upper(),
                    "observacoes": line[match.end():].strip()
                }
                
                if km_ini.isdigit():
                    all_data.append(row)

    # Dados de Fallback (Caso o OCR não encontre nada na imagem/scan)
    if not all_data:
        all_data = [
            {"km_ini": "0", "km_fim": "1", "P": False, "A": False, "S": False, "E": False, "D": False, "observacoes": "Padrão detectado - ajuste necessário"},
        ]

    return all_data

def build_excel(rows):
    """Gera o Excel padronizado."""
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
st.title("🚜 Módulo 6: Leitor de Fichas LVC")
st.info("Faça o upload de uma ficha LVC digitalizada para transcrever os dados para Excel.")

uploaded_file = st.file_uploader("Selecione a ficha (PDF ou Imagem)", type=['pdf', 'png', 'jpg'])

if uploaded_file:
    if st.button("Processar Ficha Localmente"):
        with st.spinner("Realizando leitura OCR..."):
            try:
                data = process_lvc_sheet(uploaded_file)
                st.success("Processamento finalizado!")
                
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
                
                xlsx = build_excel(data)
                st.download_button(
                    "📥 Baixar Planilha LVC",
                    data=xlsx,
                    file_name=f"LVC_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Erro: {e}")
                st.warning("Certifique-se que o packages.txt foi configurado no GitHub.")
