# pdf_tools.py (Versi Optimal)

import fitz  # PyMuPDF
import re
from pathlib import Path

def extract_pdf_fields(file_path):
    """
    Mengekstrak field dan nilainya dari teks PDF berdasarkan pola 'key: value'.
    Menggunakan Regex yang dioptimalkan untuk fleksibilitas dan kebersihan data.
    """
    try:
        with fitz.open(file_path) as doc:
            text = "".join(page.get_text("text") for page in doc)
    except Exception as e:
        print(f"Gagal membaca PDF {file_path}: {e}")
        return {}

    if not text:
        return {}
    
    # Regex Level 3: Paling fleksibel, tangguh, dan direkomendasikan.
    # Menangkap 'key' sebagai teks apa pun yang bukan titik dua, dan 'value' dengan memangkas spasi di akhir.
    pattern = r"(?:^|\n)\s*([^:\n]{3,40})\s*[:：]\s*(.+?)\s*$"
    matches = re.findall(pattern, text, re.MULTILINE) # Tambahkan flag re.MULTILINE untuk efektivitas `^` dan `$`
    
    # Membersihkan hasil dan menghindari key/value yang kosong
    detected_fields = {key.strip(): value.strip() for key, value in matches if key.strip() and value.strip()}
    return detected_fields

def process_single_pdf(file_path, template):
    """
    Memproses satu file PDF berdasarkan template yang diberikan.
    Mengembalikan (nama_file_baru, konten_asli_file) jika berhasil.
    Mengembalikan (None, None) jika gagal.
    """
    fields_in_file = extract_pdf_fields(file_path)
    if not fields_in_file:
        return None, None

    rules = template.get("aturan", [])
    separator = template.get("pemisah", " - ")
    new_name_parts = []

    for rule in rules:
        if rule in fields_in_file:
            value = fields_in_file[rule]
            # Membersihkan karakter ilegal dari nilai yang akan jadi nama file
            clean_value = re.sub(r'[\\/*?:"<>|]', '-', value)
            new_name_parts.append(clean_value)
        else:
            # Jika satu saja field dari aturan tidak ditemukan, proses file ini gagal
            return None, None

    if not new_name_parts:
        return None, None

    # Semua field ditemukan, gabungkan menjadi nama file baru
    new_name = separator.join(new_name_parts) + ".pdf"
    
    # Baca konten asli file untuk disimpan ke ZIP
    try:
        with open(file_path, 'rb') as f:
            original_content = f.read()
        return new_name, original_content
    except Exception as e:
        print(f"Gagal membaca konten file {file_path}: {e}")
        return None, None