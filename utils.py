import json
import os

TEMPLATE_FILENAME = "pdf_renamer_templates.json"

def load_templates():
    """Memuat daftar template dari file JSON."""
    if os.path.exists(TEMPLATE_FILENAME):
        try:
            with open(TEMPLATE_FILENAME, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {} # File rusak, kembalikan data kosong
    return {}

def save_templates(templates):
    """Menyimpan daftar template ke file JSON."""
    with open(TEMPLATE_FILENAME, 'w') as f:
        json.dump(templates, f, indent=4)