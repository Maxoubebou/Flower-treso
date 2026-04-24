import openpyxl
import os

path = '/home/maxime/Documents/ouest-insa2/Trésorerie/flower-treso/Ressource_gemini/doctype BV janvier 2026.xlsx'
if os.path.exists(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active
    print(f"Sheet: {sheet.title}")
    for row in sheet.iter_rows(min_row=1, max_row=40, min_col=1, max_col=10):
        for cell in row:
            if cell.value:
                print(f"{cell.coordinate}: {cell.value}")
else:
    print("File not found")
