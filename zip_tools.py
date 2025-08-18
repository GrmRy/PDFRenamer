import zipfile
import os
from pathlib import Path
import logging
import re 

class ZipError(Exception):
    pass

class ZipValidationError(Exception):
    pass

def sanitize_filename(filename):

    if not isinstance(filename, str):
        filename = str(filename)
    filename = filename.replace('/', '-').replace('\\', '-')
    cleaned_name = re.sub(r'[*:?"<>|]', '', filename).strip()
    if not cleaned_name:
        return "unnamed_file"
    return cleaned_name

def validate_zip_path(save_path):
    """Validates the ZIP file save path."""
    try:
        path_obj = Path(save_path)
        parent_dir = path_obj.parent
        if not parent_dir.exists(): return False, f"Direktori tidak ditemukan: {parent_dir}"
        if not os.access(parent_dir, os.W_OK): return False, f"Tidak ada izin menulis di direktori: {parent_dir}"
        filename = path_obj.name
        if not filename or not filename.lower().endswith('.zip'): return False, "Nama file harus berekstensi .zip"
        return True, ""
    except Exception as e:
        return False, f"Error validasi path: {str(e)}"

def validate_zip_data(renamed_data):
    """Validates the data to be zipped (simplified)."""
    if not isinstance(renamed_data, dict): return False, "Data harus berupa dictionary"
    if not renamed_data: return False, "Tidak ada data untuk di-zip"
    return True, ""

def save_zip(renamed_data, save_path):
    """
    Menyimpan data file ke dalam sebuah arsip Zip dengan validasi
    dan pembersihan nama file otomatis.
    """
    is_valid_path, path_error_msg = validate_zip_path(save_path)
    if not is_valid_path:
        raise ZipValidationError(f"Path tidak valid: {path_error_msg}")
    
    is_valid_data, data_error_msg = validate_zip_data(renamed_data)
    if not is_valid_data:
        raise ZipValidationError(f"Data tidak valid: {data_error_msg}")

    temp_path = Path(save_path).with_suffix('.tmp')
    
    try:
        logging.info(f"Membuat ZIP file dengan {len(renamed_data)} file...")
        
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for original_name, content_bytes in renamed_data.items():
                safe_name = sanitize_filename(original_name)
                
                if original_name != safe_name:
                    logging.warning(f"Nama file diubah demi keamanan: '{original_name}' -> '{safe_name}'")

                if isinstance(content_bytes, bytes) and len(content_bytes) > 0:
                    zf.writestr(safe_name, content_bytes)
                else:
                    logging.warning(f"File kosong atau konten tidak valid dilewati: {safe_name}")

        if temp_path.exists():
            temp_path.rename(save_path)
        
        logging.info(f"ZIP file berhasil dibuat: {save_path}")

    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        logging.error(f"Terjadi kesalahan saat membuat file Zip: {e}")
        raise ZipError(f"Terjadi kesalahan saat membuat file Zip: {e}")

def verify_zip_file(zip_path):
    """Verifies the integrity of a ZIP file."""
    try:
        path_obj = Path(zip_path)
        if not path_obj.exists(): return False, "File ZIP tidak ditemukan", 0
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad_files = zf.testzip()
            if bad_files: return False, f"File ZIP rusak: {bad_files}", 0
            return True, "", len(zf.namelist())
    except Exception as e:
        return False, f"Error verifikasi ZIP: {e}", 0