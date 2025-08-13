import fitz
from pathlib import Path
import re

def extract_text(pdf_path):
    with fitz.open(pdf_path) as pdf:
        return pdf[0].get_text()

def rename_pdf(original_path, new_name):
    new_path = Path(original_path).with_name(new_name + Path(original_path).suffix)
    Path(original_path).rename(new_path)
    return new_path

def process_pdfs(file_paths, pattern, progress_bar, log_area):
    compiled_pattern = re.compile(pattern)
    renamed_files = []
    total = len(file_paths)

    for i, file_path in enumerate(file_paths, start=1):
        text = extract_text(file_path)
        match = compiled_pattern.search(text)
        if match:
            new_name = match.group(1) if match.groups() else match.group(0)
            renamed_path = rename_pdf(file_path, new_name)
            renamed_files.append(renamed_path)
            log_area.append(f"✅ {file_path} → {renamed_path.name}")
        else:
            log_area.append(f"⚠️ Tidak ditemukan match di {file_path}")

        progress_bar.setValue(int(i / total * 100))

    return renamed_files
