import fitz  # PyMuPDF
import re
from pathlib import Path
import logging

class PDFProcessingError(Exception):
    """Custom exception for PDF processing errors."""
    pass

class FileValidationError(Exception):
    """Custom exception for file validation errors."""
    pass

def validate_pdf_file(file_path):
    """
    Validates if the file is a valid PDF that can be processed.
    
    Args:
        file_path (str): Path to the PDF file
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        # Check if file exists
        path_obj = Path(file_path)
        if not path_obj.exists():
            return False, f"File tidak ditemukan: {file_path}"
        
        # Check if it's a file (not directory)
        if not path_obj.is_file():
            return False, f"Path bukan file: {file_path}"
        
        # Check file extension
        if path_obj.suffix.lower() != '.pdf':
            return False, f"File bukan PDF: {file_path}"
        
        # Check file size (reasonable limits)
        file_size = path_obj.stat().st_size
        if file_size == 0:
            return False, f"File kosong: {file_path}"
        
        # Check if file size is too large (>100MB)
        max_size = 100 * 1024 * 1024  # 100MB
        if file_size > max_size:
            return False, f"File terlalu besar (>{max_size//1024//1024}MB): {file_path}"
        
        # Try to open with PyMuPDF to verify it's a valid PDF
        try:
            with fitz.open(file_path) as doc:
                if doc.page_count == 0:
                    return False, f"PDF tidak memiliki halaman: {file_path}"
        except fitz.FileDataError:
            return False, f"File PDF rusak atau terenkripsi: {file_path}"
        except fitz.FileNotFoundError:
            return False, f"File tidak dapat dibaca: {file_path}"
        except Exception as e:
            return False, f"Error membuka PDF: {str(e)}"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validasi file: {str(e)}"

def validate_template_name(name):
    """
    Validates template name for safety and usability.
    
    Args:
        name (str): Template name to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not name:
        return False, "Nama template tidak boleh kosong"
    
    name = name.strip()
    
    # Check minimum length
    if len(name) < 2:
        return False, "Nama template minimal 2 karakter"
    
    # Check maximum length
    if len(name) > 50:
        return False, "Nama template maksimal 50 karakter"
    
    # Check for invalid characters (that would cause file system issues)
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    if re.search(invalid_chars, name):
        return False, "Nama template mengandung karakter tidak valid: < > : \" / \\ | ? *"
    
    # Check for reserved names (Windows)
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
    if name.upper() in reserved_names:
        return False, f"Nama template '{name}' adalah nama yang reserved/terlarang"
    
    # Check for only whitespace
    if not name.strip():
        return False, "Nama template tidak boleh hanya spasi"
    
    return True, ""

def validate_filename_component(value):
    """
    Validates and cleans a value that will be part of a filename.
    
    Args:
        value (str): Value to be used in filename
        
    Returns:
        str: Cleaned value safe for filename
    """
    if not value:
        return ""
    
    # Remove/replace invalid filename characters
    # Windows: < > : " | ? * \ /
    # Plus control characters (0-31) and some others
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    cleaned = re.sub(invalid_chars, '-', str(value))
    
    # Remove leading/trailing dots and spaces (Windows issue)
    cleaned = cleaned.strip('. ')
    
    # Limit length to reasonable size (considering full path limits)
    max_component_length = 100
    if len(cleaned) > max_component_length:
        cleaned = cleaned[:max_component_length].rstrip('. ')
    
    return cleaned

def extract_pdf_fields(file_path):
    """
    Mengekstrak field dan nilainya dari teks PDF berdasarkan pola 'key: value'.
    Enhanced with better validation and error handling.
    
    Args:
        file_path (str): Path to PDF file
        
    Returns:
        dict: Dictionary of extracted fields
        
    Raises:
        FileValidationError: If file validation fails
        PDFProcessingError: If PDF processing fails
    """
    # Validate file first
    is_valid, error_msg = validate_pdf_file(file_path)
    if not is_valid:
        raise FileValidationError(error_msg)
    
    try:
        # Extract text from PDF
        text = ""
        with fitz.open(file_path) as doc:
            for page_num, page in enumerate(doc):
                try:
                    page_text = page.get_text("text")
                    text += page_text
                except Exception as e:
                    logging.warning(f"Gagal membaca halaman {page_num + 1} dari {file_path}: {e}")
                    continue
        
        if not text.strip():
            raise PDFProcessingError(f"Tidak ada teks yang dapat dibaca dari PDF: {file_path}")
        
    except fitz.FileDataError:
        raise PDFProcessingError(f"File PDF rusak atau terenkripsi: {file_path}")
    except fitz.FileNotFoundError:
        raise PDFProcessingError(f"File tidak ditemukan saat memproses: {file_path}")
    except Exception as e:
        raise PDFProcessingError(f"Error membaca PDF {file_path}: {str(e)}")
    
    # Extract fields using multiple patterns for better coverage
    detected_fields = {}
    
    patterns = [
        # Primary pattern: flexible key:value with colon
        r"(?:^|\n)\s*([^:\n]{3,40})\s*[:：]\s*(.+?)\s*$",
        # Secondary pattern: Label followed by value (no colon)
        r"(?:^|\n)\s*([A-Za-z][A-Za-z\s]{2,30})\s{2,}([A-Za-z0-9][^\n]{1,50})\s*$",
        # Tertiary pattern: Bold/caps labels
        r"(?:^|\n)\s*([A-Z][A-Z\s]{2,20})\s*[:：]?\s*([^\n]{1,50})\s*$"
    ]
    
    for pattern in patterns:
        try:
            matches = re.findall(pattern, text, re.MULTILINE)
            for key, value in matches:
                clean_key = key.strip()
                clean_value = value.strip()
                
                # Validate extracted fields
                if (len(clean_key) >= 3 and len(clean_value) >= 1 and 
                    len(clean_key) <= 40 and len(clean_value) <= 100):
                    # Avoid duplicates, prefer longer values
                    if clean_key not in detected_fields or len(clean_value) > len(detected_fields[clean_key]):
                        detected_fields[clean_key] = clean_value
        except re.error as e:
            logging.warning(f"Regex error dengan pattern: {pattern}, error: {e}")
            continue
    
    if not detected_fields:
        raise PDFProcessingError(f"Tidak ada field yang dapat dideteksi dari PDF: {file_path}")
    
    return detected_fields

def validate_template_rules(rules):
    """
    Validates template rules for consistency and safety.
    
    Args:
        rules (list): List of field names to use in template
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not rules:
        return False, "Template harus memiliki minimal satu field/aturan"
    
    if len(rules) > 10:
        return False, "Template tidak boleh memiliki lebih dari 10 field (untuk menghindari nama file terlalu panjang)"
    
    # Check for duplicate rules
    if len(rules) != len(set(rules)):
        return False, "Template tidak boleh memiliki field yang duplikat"
    
    # Validate each rule
    for rule in rules:
        if not rule or not rule.strip():
            return False, "Field template tidak boleh kosong"
        
        if len(rule.strip()) > 50:
            return False, f"Field template terlalu panjang (>{50} karakter): {rule}"
    
    return True, ""

def process_single_pdf(file_path, template):
    """
    Memproses satu file PDF berdasarkan template yang diberikan.
    Enhanced with comprehensive validation and error handling.
    
    Args:
        file_path (str): Path to PDF file
        template (dict): Template containing rules and separator
        
    Returns:
        tuple: (new_filename: str|None, file_content: bytes|None, error_message: str|None)
    """
    try:
        # Validate template structure
        if not isinstance(template, dict):
            return None, None, "Template harus berupa dictionary"
        
        rules = template.get("aturan", [])
        separator = template.get("pemisah", " - ")
        
        # Validate template rules
        is_valid, error_msg = validate_template_rules(rules)
        if not is_valid:
            return None, None, f"Template tidak valid: {error_msg}"
        
        # Validate separator
        if not separator or len(separator.strip()) == 0:
            separator = " - "  # Default fallback
        
        # Clean separator for filename safety
        separator = validate_filename_component(separator)
        if not separator:
            separator = "-"  # Safe fallback
        
        # Extract fields from PDF
        try:
            fields_in_file = extract_pdf_fields(file_path)
        except (FileValidationError, PDFProcessingError) as e:
            return None, None, str(e)
        
        # Check if all required fields are present
        missing_fields = []
        new_name_parts = []
        
        for rule in rules:
            if rule in fields_in_file:
                value = fields_in_file[rule]
                # Clean and validate the value for filename use
                clean_value = validate_filename_component(value)
                
                if clean_value:  # Only add non-empty cleaned values
                    new_name_parts.append(clean_value)
                else:
                    missing_fields.append(f"{rule} (nilai kosong setelah dibersihkan)")
            else:
                missing_fields.append(rule)
        
        if missing_fields:
            return None, None, f"Field tidak ditemukan atau kosong: {', '.join(missing_fields)}"
        
        if not new_name_parts:
            return None, None, "Tidak ada bagian nama file yang valid setelah pembersihan"
        
        # Create new filename
        new_name = separator.join(new_name_parts)
        
        # Final filename validation and length check
        if len(new_name) > 200:  # Leave room for .pdf extension and path
            return None, None, f"Nama file terlalu panjang ({len(new_name)} karakter), maksimal 200"
        
        new_name += ".pdf"
        
        # Read file content
        try:
            with open(file_path, 'rb') as f:
                original_content = f.read()
            
            if len(original_content) == 0:
                return None, None, "File PDF kosong"
                
            return new_name, original_content, None
            
        except PermissionError:
            return None, None, f"Tidak ada izin untuk membaca file: {file_path}"
        except FileNotFoundError:
            return None, None, f"File tidak ditemukan: {file_path}"
        except MemoryError:
            return None, None, f"File terlalu besar untuk dimuat ke memori: {file_path}"
        except Exception as e:
            return None, None, f"Error membaca file {file_path}: {str(e)}"
        
    except Exception as e:
        return None, None, f"Error tak terduga saat memproses {file_path}: {str(e)}"