import re
from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

@dataclass
class ExtractedField:
    """Data class untuk field yang diekstrak beserta metadatanya."""
    key: str
    value: str
    confidence: float
    pattern_used: str
    line_number: int

class OptimizedRegexExtractor:
    """
    Extractor regex yang dioptimalkan dengan strategi yang jauh lebih agresif
    untuk menangani format PDF yang tidak terstruktur.
    """
    
    def __init__(self):
        self.compiled_patterns = self._compile_patterns()
        
    def _compile_patterns(self) -> List[Tuple[re.Pattern, str, float]]:
        """
        **Pola Regex yang Ditulis Ulang (Lebih Agresif)**
        Menambahkan pola untuk menangkap format yang lebih liar dan tidak standar.
        """
        patterns = [
            (r"^(Nama|Tempat/Tgl Lahir|Jenis Kelamin|Alamat|Agama|Status Perkawinan|Pekerjaan|Kewarganegaraan)\s*:\s*(.+)$",
             "standard_ktp_id", 1.0),

            (r"^[ \t]*([\w\s\-\.()]{2,40}?)\s*[:：=-]\s+([^\r\n]{2,100})$",
             "flexible_separator", 0.90),
            
            (r"^[ \t]*([\w\s\-\.()]{2,40}?)[ \t]{2,}([^\r\n]{2,100})$",
             "aggressive_table", 0.70),
             
            (r"^[ \t]*([A-Z][A-Z0-9\s\-\.]{2,39})[ \t]+([^\r\n]{2,100})$",
             "aggressive_uppercase", 0.65),

            (r"^(?<=\n\s*([\w\s\-\.()]{2,40}?)\s*[:：]?\s*\n)\s*([^\r\n]{2,100})$",
             "aggressive_multiline", 0.75),
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
        """
        Ekstraksi field tingkat lanjut, memproses seluruh teks sekaligus.
        """
        if not text or not text.strip():
            return {}
        
        all_matches = []
        processed_text = '\n' + text

        for compiled_pattern, pattern_name, base_confidence in self.compiled_patterns:
            try:
                for match in compiled_pattern.finditer(processed_text):
                    groups = match.groups()
                    if len(groups) >= 2:
                        key, value = (groups[1], groups[2]) if pattern_name == 'aggressive_multiline' else (groups[0], groups[1])
                        key, value = key.strip(), value.strip()
                        
                        if not key or not value or len(key) > 40 or len(value) > 100:
                            continue
                        
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
        """
        Logika Skor Kepercayaan yang Diperbarui.
        """
        confidence = base_confidence
        key_lower = key.lower()
        
        stop_words = ['adalah', 'dengan', 'untuk', 'yang', 'dari', 'keterangan']
        if any(word in key_lower.split() for word in stop_words) or len(key.split()) > 4:
            confidence -= 0.5
        
        if len(value.split()) > 10:
            confidence -= 0.2
        if not re.search(r'[a-zA-Z0-9]', value):
            confidence -= 0.5
            
        if self._is_date_like(value): confidence += 0.15
        elif self._is_id_number_like(value): confidence += 0.20
        elif self._is_phone_like(value): confidence += 0.20
        elif self._is_email_like(value): confidence += 0.25
        
        if pattern_name == 'standard_ktp_id':
            confidence = 1.0

        return min(1.0, max(0.0, confidence))

    def _is_date_like(self, value: str) -> bool:
        return any(re.search(p, value, re.IGNORECASE) for p in [
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',
            r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)\w*\s+\d{2,4}\b'
        ])

    def _is_id_number_like(self, value: str) -> bool:
        clean_value = re.sub(r'[\s\-\.]', '', value)
        return re.match(r'^\d{15,18}$', clean_value) is not None

    def _is_phone_like(self, value: str) -> bool:
        clean_value = re.sub(r'[\s\-\(\)]', '', value)
        return re.match(r'^(\+62|62|08)\d{8,12}$', clean_value) is not None

    def _is_email_like(self, value: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value.strip()) is not None

    def _deduplicate_fields(self, matches: List[ExtractedField]) -> Dict[str, ExtractedField]:
        """
        Deduplikasi yang lebih pintar.
        """
        field_groups = {}
        for match in matches:
            normalized_key = self._normalize_field_name(match.key)
            if not normalized_key: continue
            if normalized_key not in field_groups:
                field_groups[normalized_key] = []
            field_groups[normalized_key].append(match)
        
        best_matches = {}
        for normalized_key, group in field_groups.items():
            group.sort(key=lambda x: (-x.confidence, x.line_number))
            best_match = group[0]
            best_matches[best_match.key] = best_match
        
        return best_matches

    def _normalize_field_name(self, field_name: str) -> str:
        """
        Normalisasi nama field yang lebih agresif.
        """
        normalized = field_name.lower().strip()
        normalized = re.sub(r'^[^\w]+|[^\w\s]+$', '', normalized).strip()
        
        noise_words = ['no', 'nomor', 'number', 'kode', 'id', 'tanda', 'kartu', 'isilah', 'dengan']
        words = normalized.split()
        cleaned_words = [w for w in words if w not in noise_words]
        normalized = ' '.join(cleaned_words) if cleaned_words else normalized
        
        standardizations = {
            'tgl': 'tanggal', 'telp': 'telepon', 'almt': 'alamat', 'nama lengkap': 'nama',
            'tempat tanggal lahir': 'tempat/tgl lahir'
        }
        for abbrev, full in standardizations.items():
            if normalized == abbrev:
                normalized = full
        
        return normalized

def test_regex_performance():
    """Menguji performa dan akurasi pendekatan regex baru."""
    import time
    
    sample_text = """
    Nama Lengkap: Budi Hartono
    Tempat/Tgl Lahir : Jakarta, 10-08-1990
    
    Alamat
    Jl. Merdeka No. 17, RT 01 RW 05
    Kel. Sukmajaya, Kec. Sukmajaya
    Kota Depok
    
    Status Perkawinan: Belum Kawin
    PEKERJAAN KARYAWAN SWASTA
    
    NOMOR IDENTITAS 3276011008900001
    """
    
    print("--- Memulai Pengujian Regex Agresif ---")
    extractor = OptimizedRegexExtractor()
    
    start_time = time.time()
    fields = extractor.extract_fields_advanced(sample_text)
    end_time = time.time()
    
    print(f"Selesai dalam {end_time - start_time:.4f} detik.")
    print(f"Menemukan {len(fields)} field unik:")
    
    for key, field_obj in fields.items():
        print(f"  - Key: '{key}', Value: '{field_obj.value}' (Confidence: {field_obj.confidence:.2f}, Pattern: {field_obj.pattern_used})")

if __name__ == "__main__":
    # Jalankan pengujian jika file ini dieksekusi
    test_regex_performance()