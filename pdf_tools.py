# pdf_tools.py (Enhanced with Optimized Regex Patterns)

import fitz  # PyMuPDF
import re
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

class PDFProcessingError(Exception):
    """Custom exception for PDF processing errors."""
    pass

class FileValidationError(Exception):
    """Custom exception for file validation errors."""
    pass

@dataclass
class ExtractedField:
    """Data class for extracted field with metadata."""
    key: str
    value: str
    confidence: float
    pattern_used: str
    line_number: int

class OptimizedRegexExtractor:
    """
    Optimized regex-based field extractor with multiple strategies and confidence scoring.
    """
    
    def __init__(self):
        # Compile regex patterns once for better performance
        self.compiled_patterns = self._compile_patterns()
        
    def _compile_patterns(self) -> List[Tuple[re.Pattern, str, float]]:
        """
        Compile optimized regex patterns with their names and base confidence scores.
        """
        patterns = [
            # Pattern 1: Standard colon-separated (highest confidence)
            # Matches: "Name: John Doe", "Nama: John Doe"
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "standard_colon", 0.95),
            
            # Pattern 2: Indonesian formal document patterns (very high confidence)
            # Matches common Indonesian form fields
            (r"^[ \t]*((?:Nama|Name|Nomor|Number|No|Tanggal|Date|Tempat|Place|Alamat|Address|Telepon|Phone|Email|NIK|NIP|NPWP|Status|Jenis|Type|Kelas|Class)[A-Za-z\s]*?)[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "formal_indonesian", 0.98),
            
            # Pattern 3: Uppercase labels (common in forms)
            # Matches: "NAME: JOHN DOE", "ADDRESS: STREET NAME"
            (r"^[ \t]*([A-Z][A-Z0-9\s\-\.]{2,39})[ \t]*[:：]?[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "uppercase_labels", 0.85),
            
            # Pattern 4: Numbered items (common in questionnaires)
            # Matches: "1. Name: John", "2. Address: Street"
            (r"^[ \t]*\d+\.?[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "numbered_items", 0.90),
            
            # Pattern 5: Bracket/parenthesis format
            # Matches: "[Name] John Doe", "(Address) Street Name"
            (r"^[ \t]*[\[\(]([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[\]\)][ \t]*[:：]?[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "bracketed_labels", 0.80),
            
            # Pattern 6: Table-like format with multiple spaces/tabs
            # Matches: "Name          John Doe"
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]{2,}([A-Za-z0-9][^\r\n]{0,99})[ \t]*$", 
             "table_format", 0.75),
            
            # Pattern 7: Dash-separated format
            # Matches: "Name - John Doe"
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*-[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "dash_separated", 0.70),
            
            # Pattern 8: Flexible separators (colon, equals, etc.)
            # Matches: "Name = John Doe", "Name : John Doe"
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[=|：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "flexible_separators", 0.65),
        ]
        
        compiled = []
        for pattern_str, name, confidence in patterns:
            try:
                # Use compiled patterns for better performance
                compiled_pattern = re.compile(pattern_str, re.MULTILINE)
                compiled.append((compiled_pattern, name, confidence))
            except re.error as e:
                logging.warning(f"Failed to compile regex pattern '{name}': {e}")
                continue
                
        return compiled
    
    def extract_fields_advanced(self, text: str, min_confidence: float = 0.6) -> Dict[str, ExtractedField]:
        """
        Advanced field extraction with confidence scoring and intelligent deduplication.
        
        Args:
            text: PDF text content
            min_confidence: Minimum confidence threshold for accepting fields
            
        Returns:
            Dictionary of field_name -> ExtractedField objects
        """
        if not text or not text.strip():
            return {}
        
        all_matches = []
        lines = text.split('\n')
        
        # Extract matches using all compiled patterns
        for line_num, line in enumerate(lines):
            line = line.strip()
            if len(line) < 5:  # Skip very short lines
                continue
                
            for compiled_pattern, pattern_name, base_confidence in self.compiled_patterns:
                try:
                    matches = compiled_pattern.findall(line)
                    
                    for match in matches:
                        if len(match) >= 2:
                            key, value = match[0].strip(), match[1].strip()
                            
                            # Skip if key or value is too short/long or invalid
                            if (len(key) < 2 or len(key) > 40 or 
                                len(value) < 1 or len(value) > 100):
                                continue
                            
                            # Calculate dynamic confidence based on content
                            confidence = self._calculate_confidence(
                                key, value, base_confidence, line, pattern_name
                            )
                            
                            if confidence >= min_confidence:
                                field = ExtractedField(
                                    key=key,
                                    value=value,
                                    confidence=confidence,
                                    pattern_used=pattern_name,
                                    line_number=line_num
                                )
                                all_matches.append(field)
                                
                except Exception as e:
                    logging.debug(f"Error processing line {line_num} with pattern {pattern_name}: {e}")
                    continue
        
        # Remove duplicates and return best matches
        return self._deduplicate_fields(all_matches)
    
    def _calculate_confidence(self, key: str, value: str, base_confidence: float, 
                            line: str, pattern_name: str) -> float:
        """
        Calculate dynamic confidence score based on content analysis.
        """
        confidence = base_confidence
        
        # Boost confidence for common Indonesian document fields
        common_indonesian_fields = {
            'nama', 'name', 'nomor', 'number', 'no', 'tanggal', 'date', 
            'alamat', 'address', 'telepon', 'telp', 'phone', 'email', 
            'nik', 'nip', 'npwp', 'ktp', 'id', 'status', 'jenis', 'type',
            'tempat', 'place', 'lahir', 'birth', 'kelamin', 'gender',
            'pekerjaan', 'job', 'pendidikan', 'education', 'agama', 'religion'
        }
        
        key_lower = key.lower().replace(' ', '')
        if any(common in key_lower for common in common_indonesian_fields):
            confidence += 0.15
        
        # Boost for proper field name formatting
        if key[0].isupper() and not key.isupper():  # Title Case
            confidence += 0.05
        elif key.isupper() and len(key) <= 10:  # Short uppercase (like "NIK", "NIP")
            confidence += 0.10
        
        # Analyze value content for specific patterns
        value_lower = value.lower()
        
        # High confidence for structured data
        if self._is_date_like(value):
            confidence += 0.20
        elif self._is_id_number_like(value):
            confidence += 0.25
        elif self._is_phone_like(value):
            confidence += 0.20
        elif self._is_email_like(value):
            confidence += 0.25
        elif self._is_currency_like(value):
            confidence += 0.15
        
        # Penalize problematic values
        if len(value) < 2:  # Too short
            confidence -= 0.30
        elif len(value) > 80:  # Too long
            confidence -= 0.10
        
        # Penalize if value contains too many special characters
        special_char_count = len(re.findall(r'[^\w\s\-\.,@/]', value))
        special_char_ratio = special_char_count / len(value) if len(value) > 0 else 0
        if special_char_ratio > 0.3:
            confidence -= 0.25
        
        # Penalize if key looks like content rather than a label
        if any(word in key_lower for word in ['adalah', 'ini', 'dari', 'untuk', 'dengan', 'yang']):
            confidence -= 0.40
        
        # Boost if the line formatting looks professional
        if ':' in line and line.count(':') == 1:
            confidence += 0.05
        
        # Penalize very common words that are unlikely to be field names
        common_words = {'dan', 'atau', 'dari', 'untuk', 'dengan', 'pada', 'di', 'ke', 'oleh'}
        if key_lower in common_words:
            confidence -= 0.50
        
        return min(1.0, max(0.0, confidence))
    
    def _is_date_like(self, value: str) -> bool:
        """Check if value looks like a date (Indonesian and international formats)."""
        date_patterns = [
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',  # DD/MM/YYYY, DD-MM-YYYY
            r'\b\d{2,4}[-/]\d{1,2}[-/]\d{1,2}\b',  # YYYY/MM/DD, YYYY-MM-DD
            r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4}\b',
            r'\b\d{1,2}\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{2,4}\b'
        ]
        return any(re.search(pattern, value, re.IGNORECASE) for pattern in date_patterns)
    
    def _is_id_number_like(self, value: str) -> bool:
        """Check if value looks like an Indonesian ID number."""
        clean_value = re.sub(r'[\s\-\.]', '', value)
        
        id_patterns = [
            r'^\d{16}',  # NIK (16 digits)
            r'^\d{15}',  # Old NIK format
            r'^\d{18}',  # NPWP without formatting
            r'^[A-Z]\d{7,12}',  # Employee ID patterns
            r'^\d{8,20}',  # General numeric ID
        ]
        return any(re.match(pattern, clean_value) for pattern in id_patterns)
    
    def _is_phone_like(self, value: str) -> bool:
        """Check if value looks like a phone number (Indonesian formats)."""
        clean_value = re.sub(r'[\s\-\(\)]', '', value)
        
        phone_patterns = [
            r'^(\+62|62|0)\d{8,13}',  # Indonesian mobile/landline
            r'^08\d{8,11}',  # Indonesian mobile starting with 08
            r'^021\d{7,8}',  # Jakarta landline
            r'^0\d{2,3}\d{6,8}',  # Other Indonesian landline
            r'^\+\d{10,15}',  # International format
        ]
        return any(re.match(pattern, clean_value) for pattern in phone_patterns)
    
    def _is_email_like(self, value: str) -> bool:
        """Check if value looks like an email address."""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return re.match(email_pattern, value.strip()) is not None
    
    def _is_currency_like(self, value: str) -> bool:
        """Check if value looks like currency (Rupiah or other)."""
        currency_patterns = [
            r'Rp\.?\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?',  # Rupiah: Rp. 1.000.000,00
            r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?',  # Dollar: $1,000.00
            r'\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s?rupiah',  # 1.000.000,00 rupiah
        ]
        return any(re.search(pattern, value, re.IGNORECASE) for pattern in currency_patterns)
    
    def _deduplicate_fields(self, matches: List[ExtractedField]) -> Dict[str, ExtractedField]:
        """
        Intelligent deduplication: keep the best match for each normalized field name.
        """
        if not matches:
            return {}
        
        # Group matches by normalized field name
        field_groups = {}
        for match in matches:
            normalized_key = self._normalize_field_name(match.key)
            if normalized_key not in field_groups:
                field_groups[normalized_key] = []
            field_groups[normalized_key].append(match)
        
        # Select the best match from each group
        best_matches = {}
        for normalized_key, group in field_groups.items():
            # Sort by: confidence (desc), then line number (asc), then pattern priority
            group.sort(key=lambda x: (-x.confidence, x.line_number, x.pattern_used))
            best_match = group[0]
            
            # Use the original key from the best match (preserve original formatting)
            best_matches[best_match.key] = best_match
        
        return best_matches
    
    def _normalize_field_name(self, field_name: str) -> str:
        """
        Normalize field name for intelligent deduplication.
        """
        normalized = field_name.lower().strip()
        
        # Remove common noise words
        noise_words = ['no', 'nomor', 'number', 'kode', 'code', 'id']
        words = normalized.split()
        cleaned_words = [w for w in words if w not in noise_words]
        if cleaned_words:  # Only use cleaned version if not empty
            normalized = ' '.join(cleaned_words)
        
        # Standardize common Indonesian variations
        standardizations = {
            'nm': 'nama',
            'tgl': 'tanggal',
            'telp': 'telepon',
            'hp': 'handphone',
            'almt': 'alamat',
            'tmp': 'tempat',
            'tpt': 'tempat',
            'jns': 'jenis',
            'kel': 'kelamin',
            'stat': 'status',
        }
        
        for abbrev, full in standardizations.items():
            if normalized == abbrev or normalized.endswith(' ' + abbrev):
                normalized = normalized.replace(abbrev, full)
        
        # Handle common English-Indonesian equivalents
        translations = {
            'name': 'nama',
            'date': 'tanggal',
            'address': 'alamat',
            'phone': 'telepon',
            'email': 'email',
            'status': 'status',
            'type': 'jenis',
            'place': 'tempat',
        }
        
        for eng, indo in translations.items():
            if eng in normalized:
                normalized = normalized.replace(eng, indo)
        
        return normalized

# Global instance for reuse (performance optimization)
_extractor_instance = None

def get_regex_extractor() -> OptimizedRegexExtractor:
    """Get a singleton instance of the regex extractor for better performance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = OptimizedRegexExtractor()
    return _extractor_instance

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

def extract_pdf_fields(file_path, min_confidence=0.6):
    """
    Enhanced PDF field extraction using optimized regex patterns.
    
    Args:
        file_path (str): Path to PDF file
        min_confidence (float): Minimum confidence threshold (0.0 to 1.0)
        
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
        # Extract text from PDF with page separation
        text = ""
        with fitz.open(file_path) as doc:
            for page_num, page in enumerate(doc):
                try:
                    page_text = page.get_text("text")
                    text += page_text + "\n"  # Add newline between pages
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
    
    # Use optimized extractor
    try:
        extractor = get_regex_extractor()
        extracted_fields_obj = extractor.extract_fields_advanced(text, min_confidence)
        
        # Convert ExtractedField objects to simple dict for backward compatibility
        detected_fields = {}
        for field_name, field_obj in extracted_fields_obj.items():
            detected_fields[field_name] = field_obj.value
        
        if not detected_fields:
            raise PDFProcessingError(f"Tidak ada field yang dapat dideteksi dari PDF dengan confidence >= {min_confidence}: {file_path}")
        
        # Log extraction statistics for debugging
        logging.info(f"Berhasil ekstrak {len(detected_fields)} field dari {file_path}")
        for field_name, field_obj in extracted_fields_obj.items():
            logging.debug(f"  {field_name}: {field_obj.value[:50]}... (confidence: {field_obj.confidence:.2f}, pattern: {field_obj.pattern_used})")
        
        return detected_fields
        
    except Exception as e:
        raise PDFProcessingError(f"Error saat ekstraksi field dari {file_path}: {str(e)}")

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
        
        # Extract fields from PDF using optimized extraction
        try:
            fields_in_file = extract_pdf_fields(file_path, min_confidence=0.6)
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

# Performance testing function
def test_extraction_performance(file_path: str):
    """
    Test the performance and accuracy of the optimized extraction.
    """
    import time
    
    print(f"Testing extraction on: {file_path}")
    
    start_time = time.time()
    try:
        fields = extract_pdf_fields(file_path, min_confidence=0.6)
        extraction_time = time.time() - start_time
        
        print(f"Extraction completed in: {extraction_time:.4f} seconds")
        print(f"Fields found: {len(fields)}")
        
        for field_name, value in fields.items():
            print(f"  {field_name}: {value[:50]}...")
        
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    # Example usage
    test_file = "sample.pdf"  # Replace with actual test file
    if Path(test_file).exists():
        test_extraction_performance(test_file)