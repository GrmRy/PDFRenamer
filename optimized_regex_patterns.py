import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

@dataclass
class ExtractedField:
    """Data class for extracted field with metadata."""
    key: str
    value: str
    confidence: float
    pattern_used: str
    line_number: int
    position: int

class OptimizedRegexExtractor:
    """
    Optimized regex-based field extractor with multiple strategies and confidence scoring.
    """
    
    def __init__(self):
        # Compile regex patterns once for better performance
        self.compiled_patterns = self._compile_patterns()
        
    def _compile_patterns(self) -> List[Tuple[re.Pattern, str, float]]:
        """
        Compile all regex patterns with their names and base confidence scores.
        Returns list of (compiled_pattern, pattern_name, base_confidence)
        """
        patterns = [
            # Pattern 1: Standard colon-separated (highest confidence)
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "standard_colon", 0.95),
            
            # Pattern 2: Indonesian/Formal document patterns
            (r"^[ \t]*((?:Nama|Name|Nomor|Number|No|Tanggal|Date|Tempat|Place|Alamat|Address|Telepon|Phone|Email|NIK|NIP|NPWP|Status)[A-Za-z\s]*?)[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "formal_indonesian", 0.90),
            
            # Pattern 3: Uppercase labels (common in forms)
            (r"^[ \t]*([A-Z][A-Z0-9\s\-\.]{2,39})[ \t]*[:：]?[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "uppercase_labels", 0.85),
            
            # Pattern 4: Numbered items (1. Name: Value)
            (r"^[ \t]*\d+\.?[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[:：][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "numbered_items", 0.80),
            
            # Pattern 5: Bracket/parenthesis format [Label] Value
            (r"^[ \t]*[\[\(]([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[\]\)][ \t]*[:：]?[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "bracketed_labels", 0.75),
            
            # Pattern 6: Table-like format with multiple spaces/tabs
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]{2,}([^\r\n]{1,100})[ \t]*$", 
             "table_format", 0.70),
            
            # Pattern 7: Dash-separated format (Label - Value)
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*-[ \t]*([^\r\n]{1,100})[ \t]*$", 
             "dash_separated", 0.65),
            
            # Pattern 8: Flexible key-value with various separators
            (r"^[ \t]*([A-Za-z][A-Za-z0-9\s\-\.]{2,39})[ \t]*[:|：|=][ \t]*([^\r\n]{1,100})[ \t]*$", 
             "flexible_separators", 0.60),
        ]
        
        compiled = []
        for pattern_str, name, confidence in patterns:
            try:
                compiled_pattern = re.compile(pattern_str, re.MULTILINE | re.IGNORECASE)
                compiled.append((compiled_pattern, name, confidence))
            except re.error as e:
                logging.warning(f"Failed to compile pattern '{name}': {e}")
                continue
                
        return compiled
    
    def extract_fields_advanced(self, text: str, min_confidence: float = 0.5) -> Dict[str, ExtractedField]:
        """
        Advanced field extraction with confidence scoring and deduplication.
        
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
        
        # Extract matches from all patterns
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 5:  # Skip very short lines
                continue
                
            for compiled_pattern, pattern_name, base_confidence in self.compiled_patterns:
                matches = compiled_pattern.findall(line)
                
                for match in matches:
                    if len(match) >= 2:
                        key, value = match[0].strip(), match[1].strip()
                        
                        # Calculate dynamic confidence
                        confidence = self._calculate_confidence(
                            key, value, base_confidence, line, pattern_name
                        )
                        
                        if confidence >= min_confidence:
                            field = ExtractedField(
                                key=key,
                                value=value,
                                confidence=confidence,
                                pattern_used=pattern_name,
                                line_number=line_num,
                                position=line.find(key)
                            )
                            all_matches.append(field)
        
        # Deduplicate and select best matches
        return self._deduplicate_fields(all_matches)
    
    def _calculate_confidence(self, key: str, value: str, base_confidence: float, 
                            line: str, pattern_name: str) -> float:
        """
        Calculate dynamic confidence score based on various factors.
        """
        confidence = base_confidence
        
        # Boost confidence for common field names
        common_fields = {
            'name', 'nama', 'number', 'nomor', 'date', 'tanggal', 
            'address', 'alamat', 'phone', 'telepon', 'email', 
            'nik', 'nip', 'npwp', 'ktp', 'id'
        }
        
        key_lower = key.lower()
        if any(common in key_lower for common in common_fields):
            confidence += 0.1
        
        # Boost for proper capitalization
        if key[0].isupper() and not key.isupper():
            confidence += 0.05
        
        # Penalize very long keys (probably not field names)
        if len(key) > 30:
            confidence -= 0.2
        
        # Penalize very short or very long values
        if len(value) < 2:
            confidence -= 0.3
        elif len(value) > 80:
            confidence -= 0.1
        
        # Boost for values that look like specific data types
        if self._is_date_like(value):
            confidence += 0.15
        elif self._is_id_like(value):
            confidence += 0.1
        elif self._is_phone_like(value):
            confidence += 0.1
        elif self._is_email_like(value):
            confidence += 0.15
        
        # Penalize if value contains too many special characters
        special_char_ratio = len(re.findall(r'[^\w\s\-\.,@]', value)) / len(value)
        if special_char_ratio > 0.3:
            confidence -= 0.2
        
        # Boost if the line looks well-formatted
        if ':' in line and line.count(':') == 1:
            confidence += 0.05
        
        return min(1.0, max(0.0, confidence))
    
    def _is_date_like(self, value: str) -> bool:
        """Check if value looks like a date."""
        date_patterns = [
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{2,4}[-/]\d{1,2}[-/]\d{1,2}',  # YYYY/MM/DD or YYYY-MM-DD
            r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2,4}',
            r'\d{1,2}\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+\d{2,4}'
        ]
        return any(re.search(pattern, value, re.IGNORECASE) for pattern in date_patterns)
    
    def _is_id_like(self, value: str) -> bool:
        """Check if value looks like an ID number."""
        # Indonesian ID patterns
        id_patterns = [
            r'^\d{16}$',  # NIK (16 digits)
            r'^\d{15}$',  # Old NIK (15 digits)
            r'^\d{18}$',  # NPWP without dots
            r'^\d{2}\.\d{3}\.\d{3}\.\d{1}-\d{3}\.\d{3}$',  # NPWP with dots
            r'^[A-Z]\d{7}$',  # Some ID formats
            r'^\d{8,20}$',  # General numeric ID
        ]
        return any(re.match(pattern, value.replace(' ', '').replace('.', '').replace('-', '')) for pattern in id_patterns)
    
    def _is_phone_like(self, value: str) -> bool:
        """Check if value looks like a phone number."""
        phone_patterns = [
            r'^[\+]?[0-9\s\-\(\)]{8,15}$',  # General phone pattern
            r'^(\+62|62|0)\d{8,12}$',  # Indonesian phone
        ]
        clean_value = re.sub(r'[\s\-\(\)]', '', value)
        return any(re.match(pattern, clean_value) for pattern in phone_patterns)
    
    def _is_email_like(self, value: str) -> bool:
        """Check if value looks like an email."""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, value.strip()) is not None
    
    def _deduplicate_fields(self, matches: List[ExtractedField]) -> Dict[str, ExtractedField]:
        """
        Remove duplicates and select the best match for each field name.
        """
        field_groups = {}
        
        # Group matches by normalized field name
        for match in matches:
            normalized_key = self._normalize_field_name(match.key)
            if normalized_key not in field_groups:
                field_groups[normalized_key] = []
            field_groups[normalized_key].append(match)
        
        # Select best match from each group
        best_matches = {}
        for normalized_key, group in field_groups.items():
            # Sort by confidence (desc), then by line number (asc)
            group.sort(key=lambda x: (-x.confidence, x.line_number))
            best_match = group[0]
            
            # Use the original key from the best match
            best_matches[best_match.key] = best_match
        
        return best_matches
    
    def _normalize_field_name(self, field_name: str) -> str:
        """
        Normalize field name for deduplication.
        """
        normalized = field_name.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes = ['no', 'nomor', 'number', 'kode', 'code']
        suffixes = ['name', 'nama', 'date', 'tanggal']
        
        for prefix in prefixes:
            if normalized.startswith(prefix + ' '):
                normalized = normalized[len(prefix):].strip()
        
        for suffix in suffixes:
            if normalized.endswith(' ' + suffix):
                normalized = normalized[:-len(suffix)].strip()
        
        # Standardize common variations
        standardizations = {
            'nm': 'nama',
            'tgl': 'tanggal',
            'telp': 'telepon',
            'hp': 'handphone',
            'almt': 'alamat',
        }
        
        for abbrev, full in standardizations.items():
            if normalized == abbrev:
                normalized = full
                break
        
        return normalized

# Enhanced extract_pdf_fields function using the optimized extractor
def extract_pdf_fields_optimized(file_path: str, min_confidence: float = 0.6) -> Dict[str, str]:
    """
    Optimized version of extract_pdf_fields with better regex patterns and confidence scoring.
    
    Args:
        file_path: Path to PDF file
        min_confidence: Minimum confidence threshold (0.0 to 1.0)
    
    Returns:
        Dictionary of field_name -> value
    """
    from pdf_tools import validate_pdf_file, FileValidationError, PDFProcessingError
    import fitz
    
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
                    text += page_text + "\n"  # Add newline between pages
                except Exception as e:
                    logging.warning(f"Failed to read page {page_num + 1} from {file_path}: {e}")
                    continue
        
        if not text.strip():
            raise PDFProcessingError(f"No readable text found in PDF: {file_path}")
        
        # Use optimized extractor
        extractor = OptimizedRegexExtractor()
        extracted_fields = extractor.extract_fields_advanced(text, min_confidence)
        
        # Convert ExtractedField objects to simple dict
        result = {}
        for field_name, field_obj in extracted_fields.items():
            result[field_name] = field_obj.value
        
        if not result:
            raise PDFProcessingError(f"No fields detected in PDF with confidence >= {min_confidence}: {file_path}")
        
        # Log extraction statistics
        logging.info(f"Extracted {len(result)} fields from {file_path}")
        for field_name, field_obj in extracted_fields.items():
            logging.debug(f"  {field_name}: {field_obj.value[:50]}... (confidence: {field_obj.confidence:.2f}, pattern: {field_obj.pattern_used})")
        
        return result
        
    except fitz.FileDataError:
        raise PDFProcessingError(f"Corrupted or encrypted PDF file: {file_path}")
    except fitz.FileNotFoundError:
        raise PDFProcessingError(f"File not found during processing: {file_path}")
    except Exception as e:
        raise PDFProcessingError(f"Error reading PDF {file_path}: {str(e)}")

# Performance testing function
def test_regex_performance():
    """Test performance of different regex approaches."""
    import time
    
    sample_text = """
    Nama: John Doe
    Nomor KTP: 1234567890123456
    Tanggal Lahir: 15 Januari 1990
    Alamat: Jl. Sudirman No. 123, Jakarta
    Telepon: +62 21 12345678
    Email: john.doe@example.com
    Status: Aktif
    
    NAME: JANE SMITH
    ID NUMBER: 9876543210987654
    BIRTH DATE: 25/12/1985
    ADDRESS: 456 Main Street, City
    PHONE: 081234567890
    STATUS: ACTIVE
    
    1. Full Name: Bob Johnson
    2. Employee ID: EMP001234
    3. Department: IT Department
    4. Salary: $5000
    5. Start Date: 2020-01-15
    """
    
    # Test old method
    old_pattern = r"(?:^|\n)\s*([^:\n]{3,40})\s*[:：]\s*(.+?)\s*$"
    
    start_time = time.time()
    for _ in range(1000):
        matches = re.findall(old_pattern, sample_text, re.MULTILINE)
    old_time = time.time() - start_time
    
    # Test new method
    extractor = OptimizedRegexExtractor()
    
    start_time = time.time()
    for _ in range(1000):
        fields = extractor.extract_fields_advanced(sample_text)
    new_time = time.time() - start_time
    
    print(f"Old method: {old_time:.4f}s")
    print(f"New method: {new_time:.4f}s")
    print(f"Performance difference: {((new_time - old_time) / old_time * 100):+.1f}%")
    
    # Show quality comparison
    old_matches = re.findall(old_pattern, sample_text, re.MULTILINE)
    new_fields = extractor.extract_fields_advanced(sample_text)
    
    print(f"\nOld method found: {len(old_matches)} matches")
    print(f"New method found: {len(new_fields)} fields")
    
    print("\nNew method results with confidence scores:")
    for name, field in new_fields.items():
        print(f"  {name}: {field.value} (confidence: {field.confidence:.2f})")

if __name__ == "__main__":
    test_regex_performance()