import fitz  # PyMuPDF
import re
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from universal_extractor import run_universal_extraction, BUILT_IN_TEMPLATES

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
    Extractor regex yang dioptimalkan dengan strategi agresif
    untuk menangani format PDF yang tidak terstruktur saat membuat template custom.
    """
    def __init__(self):
        self.compiled_patterns = self._compile_patterns()
        
    def _compile_patterns(self) -> List[Tuple[re.Pattern, str, float]]:
        patterns = [
            (r"^(Nama|Tempat/Tgl Lahir|Jenis Kelamin|Alamat|Agama|Status Perkawinan|Pekerjaan|Kewarganegaraan)\s*:\s*(.+)$", "standard_ktp_id", 1.0),
            (r"^[ \t]*([\w\s\-\.()]{2,40}?)\s*[:：=-]\s+([^\r\n]{2,100})$", "flexible_separator", 0.90),
            (r"^[ \t]*([\w\s\-\.()]{2,40}?)[ \t]{2,}([^\r\n]{2,100})$", "aggressive_table", 0.70),
            (r"^[ \t]*([A-Z][A-Z0-9\s\-\.]{2,39})[ \t]+([^\r\n]{2,100})$", "aggressive_uppercase", 0.65),
            (r"^(?<=\n\s*([\w\s\-\.()]{2,40}?)\s*[:：]?\s*\n)\s*([^\r\n]{2,100})$", "aggressive_multiline", 0.75),
        ]
        compiled = []
        for pattern_str, name, confidence in patterns:
            try:
                compiled_pattern = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
                compiled.append((compiled_pattern, name, confidence))
            except re.error as e:
                logging.warning(f"Gagal mengompilasi pola regex '{name}': {e}")
        return compiled
    
    def extract_fields_advanced(self, text: str, min_confidence: float = 0.55) -> Dict[str, ExtractedField]:
        if not text or not text.strip(): return {}
        all_matches = []
        processed_text = '\n' + text
        for compiled_pattern, pattern_name, base_confidence in self.compiled_patterns:
            try:
                for match in compiled_pattern.finditer(processed_text):
                    groups = match.groups()
                    if len(groups) >= 2:
                        key, value = (groups[1], groups[2]) if pattern_name == 'aggressive_multiline' else (groups[0], groups[1])
                        key, value = key.strip(), value.strip()
                        if not key or not value or len(key) > 40 or len(value) > 100: continue
                        line_number = processed_text.count('\n', 0, match.start())
                        confidence = self._calculate_confidence(key, value, base_confidence, pattern_name)
                        if confidence >= min_confidence:
                            all_matches.append(ExtractedField(
                                key=key, value=value, confidence=confidence,
                                pattern_used=pattern_name, line_number=line_number
                            ))
            except Exception as e:
                logging.debug(f"Error saat memproses dengan pola {pattern_name}: {e}")
        return self._deduplicate_fields(all_matches)

    def _calculate_confidence(self, key: str, value: str, base_confidence: float, pattern_name: str) -> float:
        confidence = base_confidence
        key_lower = key.lower()
        stop_words = ['adalah', 'dengan', 'untuk', 'yang', 'dari', 'keterangan']
        if any(word in key_lower.split() for word in stop_words) or len(key.split()) > 4: confidence -= 0.5
        if len(value.split()) > 10: confidence -= 0.2
        if not re.search(r'[a-zA-Z0-9]', value): confidence -= 0.5
        if self._is_date_like(value): confidence += 0.15
        elif self._is_id_number_like(value): confidence += 0.20
        elif self._is_phone_like(value): confidence += 0.20
        elif self._is_email_like(value): confidence += 0.25
        if pattern_name == 'standard_ktp_id': confidence = 1.0
        return min(1.0, max(0.0, confidence))

    def _is_date_like(self, value: str) -> bool: return any(re.search(p, value, re.IGNORECASE) for p in [r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)\w*\s+\d{2,4}\b'])
    def _is_id_number_like(self, value: str) -> bool: return re.match(r'^\d{15,18}$', re.sub(r'[\s\-\.]', '', value)) is not None
    def _is_phone_like(self, value: str) -> bool: return re.match(r'^(\+62|62|08)\d{8,12}$', re.sub(r'[\s\-\(\)]', '', value)) is not None
    def _is_email_like(self, value: str) -> bool: return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value.strip()) is not None

    def _deduplicate_fields(self, matches: List[ExtractedField]) -> Dict[str, ExtractedField]:
        field_groups = {}
        for match in matches:
            normalized_key = self._normalize_field_name(match.key)
            if not normalized_key: continue
            if normalized_key not in field_groups: field_groups[normalized_key] = []
            field_groups[normalized_key].append(match)
        best_matches = {}
        for normalized_key, group in field_groups.items():
            group.sort(key=lambda x: (-x.confidence, x.line_number))
            best_match = group[0]
            best_matches[best_match.key] = best_match
        return best_matches

    def _normalize_field_name(self, field_name: str) -> str:
        normalized = field_name.lower().strip()
        normalized = re.sub(r'^[^\w]+|[^\w\s]+$', '', normalized).strip()
        noise_words = ['no', 'nomor', 'number', 'kode', 'id', 'tanda', 'kartu', 'isilah', 'dengan']
        words = normalized.split()
        cleaned_words = [w for w in words if w not in noise_words]
        normalized = ' '.join(cleaned_words) if cleaned_words else normalized
        standardizations = {'tgl': 'tanggal', 'telp': 'telepon', 'almt': 'alamat', 'nama lengkap': 'nama', 'tempat tanggal lahir': 'tempat/tgl lahir'}
        for abbrev, full in standardizations.items():
            if normalized == abbrev: normalized = full
        return normalized

_extractor_instance = None
def get_regex_extractor() -> OptimizedRegexExtractor:
    global _extractor_instance
    if _extractor_instance is None: _extractor_instance = OptimizedRegexExtractor()
    return _extractor_instance

def validate_pdf_file(file_path):
    try:
        path_obj = Path(file_path)
        if not path_obj.exists(): return False, f"File tidak ditemukan: {file_path}"
        if not path_obj.is_file(): return False, f"Path bukan file: {file_path}"
        if path_obj.suffix.lower() != '.pdf': return False, f"File bukan PDF: {file_path}"
        file_size = path_obj.stat().st_size
        if file_size == 0: return False, f"File kosong: {file_path}"
        max_size = 100 * 1024 * 1024
        if file_size > max_size: return False, f"File terlalu besar (>{max_size//1024//1024}MB): {file_path}"
        with fitz.open(file_path) as doc:
            if doc.page_count == 0: return False, f"PDF tidak memiliki halaman: {file_path}"
        return True, ""
    except Exception as e:
        return False, f"Error validasi file: {str(e)}"

def validate_template_name(name):
    if not name or not name.strip(): return False, "Nama template tidak boleh kosong"
    if len(name) < 2: return False, "Nama template minimal 2 karakter"
    if len(name) > 50: return False, "Nama template maksimal 50 karakter"
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name): return False, "Nama template mengandung karakter tidak valid"
    reserved = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
    if name.upper() in reserved: return False, "Nama template adalah nama yang terlarang"
    return True, ""

def validate_filename_component(value):
    if not value: return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value)).strip('. ')
    return cleaned[:100].rstrip('. ')

def extract_pdf_fields(file_path, min_confidence=0.55):
    is_valid, error_msg = validate_pdf_file(file_path)
    if not is_valid: raise FileValidationError(error_msg)
    try:
        text = "".join(page.get_text("text") for page in fitz.open(file_path))
        if not text.strip(): raise PDFProcessingError("Tidak ada teks yang dapat dibaca.")
        extractor = get_regex_extractor()
        extracted_fields_obj = extractor.extract_fields_advanced(text, min_confidence)
        detected_fields = {field_name: field_obj.value for field_name, field_obj in extracted_fields_obj.items()}
        if not detected_fields: raise PDFProcessingError("Tidak ada field yang dapat dideteksi.")
        return detected_fields
    except Exception as e:
        raise PDFProcessingError(f"Error saat ekstraksi field: {str(e)}")

def validate_template_rules(rules):
    if not rules: return False, "Template harus memiliki minimal satu aturan"
    if len(rules) > 10: return False, "Template maksimal memiliki 10 aturan"
    if len(rules) != len(set(rules)): return False, "Template tidak boleh memiliki aturan duplikat"
    for rule in rules:
        if not rule or not rule.strip(): return False, "Aturan template tidak boleh kosong"
        if len(rule.strip()) > 50: return False, f"Aturan template terlalu panjang: {rule}"
    return True, ""

def process_pdf_with_built_in_template(file_path, template_name):
    """Memproses PDF menggunakan SATU pola spesifik dari template bawaan."""
    try:
        is_valid, error_msg = validate_pdf_file(file_path)
        if not is_valid: return None, None, error_msg

        text = "".join(page.get_text("text", sort=True) for page in fitz.open(file_path))
        if not text.strip(): return None, None, "Tidak ada teks yang dapat dibaca dari PDF."

        new_name = run_universal_extraction(text, template_name)
        if not new_name: return None, None, f"Pola '{template_name}' tidak cocok dengan dokumen ini."

        with open(file_path, 'rb') as f: content = f.read()
        return new_name, content, None
    except Exception as e:
        return None, None, f"Error saat memproses dengan template bawaan: {str(e)}"

def process_single_pdf(file_path, template, template_name):
    """Memproses satu file PDF berdasarkan template (custom atau bawaan)."""
    if template_name in BUILT_IN_TEMPLATES:
        return process_pdf_with_built_in_template(file_path, template_name)

    try:
        if not isinstance(template, dict): return None, None, "Template harus berupa dictionary"
        
        rules = template.get("aturan", [])
        separator = template.get("pemisah", " - ")
        
        is_valid, error_msg = validate_template_rules(rules)
        if not is_valid: return None, None, f"Template tidak valid: {error_msg}"
        
        separator = validate_filename_component(separator) or "-"
        fields_in_file = extract_pdf_fields(file_path, min_confidence=0.55)
        
        missing_fields, new_name_parts = [], []
        for rule in rules:
            found_key = next((k for k in fields_in_file if k.lower() == rule.lower()), None)
            if found_key:
                clean_value = validate_filename_component(fields_in_file[found_key])
                if clean_value: new_name_parts.append(clean_value)
                else: missing_fields.append(f"{rule} (nilai kosong)")
            else:
                missing_fields.append(rule)
        
        if missing_fields: return None, None, f"Field tidak ditemukan: {', '.join(missing_fields)}"
        if not new_name_parts: return None, None, "Tidak ada bagian nama file yang valid."
        
        new_name = separator.join(new_name_parts) + ".pdf"
        if len(new_name) > 220: return None, None, "Nama file hasil terlalu panjang."
        
        with open(file_path, 'rb') as f: original_content = f.read()
        return new_name, original_content, None
            
    except (FileValidationError, PDFProcessingError) as e:
        return None, None, str(e)
    except Exception as e:
        return None, None, f"Error tak terduga saat memproses {file_path}: {str(e)}"