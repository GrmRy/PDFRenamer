import zipfile
import os
from pathlib import Path
import logging

class ZipError(Exception):
    """Custom exception untuk error terkait Zip."""
    pass

class ZipValidationError(Exception):
    """Custom exception untuk error validasi ZIP."""
    pass

def validate_zip_path(save_path):
    """
    Validates the ZIP file save path.
    
    Args:
        save_path (str): Path where ZIP file will be saved
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        path_obj = Path(save_path)
        
        # Check if parent directory exists and is writable
        parent_dir = path_obj.parent
        if not parent_dir.exists():
            return False, f"Direktori tidak ditemukan: {parent_dir}"
        
        if not parent_dir.is_dir():
            return False, f"Path parent bukan direktori: {parent_dir}"
        
        # Check write permissions
        if not os.access(parent_dir, os.W_OK):
            return False, f"Tidak ada izin menulis di direktori: {parent_dir}"
        
        # Check if file already exists
        if path_obj.exists():
            if not path_obj.is_file():
                return False, f"Path sudah ada dan bukan file: {save_path}"
            
            # Check if existing file is writable
            if not os.access(path_obj, os.W_OK):
                return False, f"File sudah ada dan tidak dapat ditimpa: {save_path}"
        
        # Check filename
        filename = path_obj.name
        if not filename:
            return False, "Nama file tidak boleh kosong"
        
        # Check for invalid characters in filename
        invalid_chars = '<>:"|?*'
        if any(char in filename for char in invalid_chars):
            return False, f"Nama file mengandung karakter tidak valid: {invalid_chars}"
        
        # Check extension
        if not filename.lower().endswith('.zip'):
            return False, "File harus berekstensi .zip"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validasi path: {str(e)}"

def validate_zip_data(renamed_data):
    """
    Validates the data to be zipped.
    
    Args:
        renamed_data (dict): Dictionary of {filename: content}
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not isinstance(renamed_data, dict):
        return False, "Data harus berupa dictionary"
    
    if len(renamed_data) == 0:
        return False, "Tidak ada data untuk di-zip"
    
    if len(renamed_data) > 10000:  # Reasonable limit
        return False, f"Terlalu banyak file ({len(renamed_data)}), maksimal 10000"
    
    total_size = 0
    max_individual_size = 500 * 1024 * 1024  # 500MB per file
    max_total_size = 2 * 1024 * 1024 * 1024  # 2GB total
    
    for filename, content in renamed_data.items():
        # Validate filename
        if not isinstance(filename, str) or not filename.strip():
            return False, f"Nama file tidak valid: {filename}"
        
        # Check filename length
        if len(filename) > 255:
            return False, f"Nama file terlalu panjang: {filename[:50]}..."
        
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/') or '\\' in filename:
            return False, f"Nama file mengandung path yang tidak aman: {filename}"
        
        # Validate content
        if not isinstance(content, bytes):
            return False, f"Konten file harus berupa bytes: {filename}"
        
        # Check individual file size
        content_size = len(content)
        if content_size > max_individual_size:
            return False, f"File terlalu besar ({content_size / 1024 / 1024:.1f}MB): {filename}"
        
        total_size += content_size
    
    # Check total size
    if total_size > max_total_size:
        return False, f"Total ukuran terlalu besar ({total_size / 1024 / 1024 / 1024:.1f}GB), maksimal 2GB"
    
    return True, ""

def estimate_zip_size(renamed_data):
    """
    Estimates the final ZIP file size (rough calculation).
    
    Args:
        renamed_data (dict): Dictionary of {filename: content}
        
    Returns:
        int: Estimated ZIP size in bytes
    """
    # Rough estimation: assume 60% compression ratio for typical PDF files
    total_uncompressed = sum(len(content) for content in renamed_data.values())
    estimated_compressed = int(total_uncompressed * 0.6)
    
    # Add overhead for ZIP structure (headers, directory, etc.)
    overhead = len(renamed_data) * 100 + 1024  # Rough estimate
    
    return estimated_compressed + overhead

def save_zip(renamed_data, save_path):
    """
    Menyimpan data file ke dalam sebuah arsip Zip dengan validasi yang enhanced.
    
    Args:
        renamed_data (dict): Dictionary {nama_file_baru: konten_bytes}
        save_path (str): Path untuk menyimpan file ZIP
        
    Raises:
        ZipValidationError: If validation fails
        ZipError: If ZIP creation fails
    """
    # Validate inputs
    is_valid, error_msg = validate_zip_data(renamed_data)
    if not is_valid:
        raise ZipValidationError(f"Data tidak valid: {error_msg}")
    
    is_valid, error_msg = validate_zip_path(save_path)
    if not is_valid:
        raise ZipValidationError(f"Path tidak valid: {error_msg}")
    
    # Check available disk space
    try:
        estimated_size = estimate_zip_size(renamed_data)
        available_space = os.statvfs(Path(save_path).parent).f_bavail * os.statvfs(Path(save_path).parent).f_frsize
        
        if estimated_size > available_space:
            raise ZipError(f"Tidak cukup ruang disk. Diperlukan: {estimated_size / 1024 / 1024:.1f}MB, Tersedia: {available_space / 1024 / 1024:.1f}MB")
    except AttributeError:
        # os.statvfs not available on Windows, use different method
        try:
            import shutil
            available_space = shutil.disk_usage(Path(save_path).parent).free
            if estimated_size > available_space:
                raise ZipError(f"Tidak cukup ruang disk. Diperlukan: {estimated_size / 1024 / 1024:.1f}MB, Tersedia: {available_space / 1024 / 1024:.1f}MB")
        except Exception:
            # If we can't check disk space, continue with a warning
            logging.warning("Tidak dapat memeriksa ruang disk yang tersedia")
    
    # Create temporary file for atomic operation
    temp_path = Path(save_path).with_suffix('.tmp')
    
    try:
        logging.info(f"Membuat ZIP file dengan {len(renamed_data)} file...")
        
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            files_added = 0
            
            for new_name, content_bytes in renamed_data.items():
                try:
                    # Double-check content before adding
                    if not isinstance(content_bytes, bytes):
                        raise ZipError(f"Konten bukan bytes untuk file: {new_name}")
                    
                    if len(content_bytes) == 0:
                        logging.warning(f"File kosong dilewati: {new_name}")
                        continue
                    
                    # Add file to ZIP
                    zf.writestr(new_name, content_bytes)
                    files_added += 1
                    
                    # Log progress for large operations
                    if files_added % 100 == 0:
                        logging.info(f"Progress: {files_added}/{len(renamed_data)} file ditambahkan")
                        
                except Exception as e:
                    logging.error(f"Error menambahkan file {new_name}: {e}")
                    raise ZipError(f"Gagal menambahkan file '{new_name}': {e}")
        
        if files_added == 0:
            raise ZipError("Tidak ada file yang berhasil ditambahkan ke ZIP")
        
        # Verify the ZIP file was created correctly
        try:
            with zipfile.ZipFile(temp_path, 'r') as zf:
                # Test the ZIP file integrity
                bad_files = zf.testzip()
                if bad_files:
                    raise ZipError(f"ZIP file rusak, file bermasalah: {bad_files}")
                
                # Verify file count
                zip_file_count = len(zf.namelist())
                if zip_file_count != files_added:
                    raise ZipError(f"Jumlah file tidak sesuai. Diharapkan: {files_added}, Ditemukan: {zip_file_count}")
                
        except zipfile.BadZipFile:
            raise ZipError("File ZIP yang dibuat rusak")
        
        # Atomic move: replace target with temp file
        if Path(save_path).exists():
            # Create backup of existing file
            backup_path = Path(save_path).with_suffix('.backup')
            try:
                Path(save_path).rename(backup_path)
            except Exception as e:
                raise ZipError(f"Gagal membuat backup file existing: {e}")
        
        try:
            temp_path.rename(save_path)
        except Exception as e:
            # Try to restore backup if move failed
            if Path(save_path).with_suffix('.backup').exists():
                try:
                    Path(save_path).with_suffix('.backup').rename(save_path)
                except Exception:
                    pass
            raise ZipError(f"Gagal memindahkan file sementara ke target: {e}")
        
        # Clean up backup if successful
        backup_path = Path(save_path).with_suffix('.backup')
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass  # Not critical if backup cleanup fails
        
        # Final verification
        final_size = Path(save_path).stat().st_size
        logging.info(f"ZIP file berhasil dibuat: {save_path} ({final_size / 1024 / 1024:.1f}MB, {files_added} file)")
        
    except PermissionError as e:
        raise ZipError(f"Tidak ada izin untuk menulis di lokasi yang dipilih: {e}")
        
    except OSError as e:
        if e.errno == 28:  # No space left on device
            raise ZipError("Tidak cukup ruang disk untuk menyimpan file ZIP")
        else:
            raise ZipError(f"Error sistem saat membuat ZIP: {e}")
            
    except zipfile.LargeZipFile:
        raise ZipError("File ZIP terlalu besar (>4GB). Coba kurangi jumlah atau ukuran file.")
        
    except Exception as e:
        raise ZipError(f"Terjadi kesalahan tak terduga saat membuat file Zip: {e}")
        
    finally:
        # Clean up temporary file if it still exists
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass  # Not critical if cleanup fails

def verify_zip_file(zip_path):
    """
    Verifies the integrity of a ZIP file.
    
    Args:
        zip_path (str): Path to ZIP file to verify
        
    Returns:
        tuple: (is_valid: bool, error_message: str, file_count: int)
    """
    try:
        path_obj = Path(zip_path)
        
        if not path_obj.exists():
            return False, "File ZIP tidak ditemukan", 0
        
        if not path_obj.is_file():
            return False, "Path bukan file", 0
        
        if path_obj.stat().st_size == 0:
            return False, "File ZIP kosong", 0
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Test ZIP integrity
            bad_files = zf.testzip()
            if bad_files:
                return False, f"File ZIP rusak: {bad_files}", 0
            
            # Count files
            file_count = len(zf.namelist())
            
            return True, "", file_count
            
    except zipfile.BadZipFile:
        return False, "File bukan ZIP yang valid", 0
    except PermissionError:
        return False, "Tidak ada izin untuk membaca file ZIP", 0
    except Exception as e:
        return False, f"Error verifikasi ZIP: {e}", 0