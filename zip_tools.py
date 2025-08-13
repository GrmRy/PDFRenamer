import zipfile

class ZipError(Exception):
    """Custom exception untuk error terkait Zip."""
    pass

def save_zip(renamed_data, save_path):
    """
    Menyimpan data file ke dalam sebuah arsip Zip.
    renamed_data adalah dictionary {nama_file_baru: konten_bytes}.
    """
    try:
        with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for new_name, content_bytes in renamed_data.items():
                zf.writestr(new_name, content_bytes)
    except PermissionError:
        raise ZipError("Tidak ada izin untuk menulis di lokasi yang dipilih.")
    except Exception as e:
        raise ZipError(f"Terjadi kesalahan saat membuat file Zip: {e}")