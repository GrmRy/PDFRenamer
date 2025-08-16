import re

def clean_filename(name):
    """Membersihkan nama file dari karakter yang tidak diizinkan."""
    return re.sub(r'[\\/*?:"<>|]', '-', name)


def try_faktur_pattern(text):
    """Mencoba pola dari faktur.py."""
    referensi_match = re.search(r"\(Referensi:\s*(.*?)\)", text)
    if referensi_match:
        pattern_nama = r"Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak:\s*\nNama\s*[:：]\s*(.*?)\s*(?:\n|$)"
        nama_match = re.search(pattern_nama, text)
        if nama_match:
            referensi = clean_filename(referensi_match.group(1).strip())
            nama = nama_match.group(1).strip()
            return f"{referensi} {nama}.pdf"
    return None

def try_faktur_masukan_pattern(text):
    """Mencoba pola dari faktur_masukan.py."""
    referensi_match = re.search(r"\(Referensi:\s*([^)]+)\)", text)
    if referensi_match:
        pattern_nama = r"Pengusaha Kena Pajak:\s*\nNama\s*[:：]\s*(.*?)\s*(?:\n|$)"
        nama_match = re.search(pattern_nama, text)
        if nama_match:
            referensi = clean_filename(referensi_match.group(1).strip())
            nama = nama_match.group(1).strip()
            return f"{nama} {referensi}.pdf"
    return None

def try_faktur_penjualan_pattern(text):
    """Mencoba pola dari fakturPenjualan.py."""
    pola = r"No\.\s*Faktur\s*[:：]\s*(\S+)"
    match = re.search(pola, text)
    if match:
        referensi = match.group(1).strip().replace('/', '-')
        referensi = clean_filename(referensi)
        return f"No Faktur - {referensi}.pdf"
    return None

def try_bukti_potong_pattern(text):
    """Mencoba pola dari bukti_potong.py."""
    pola_masa = r"MASA PAJAK.*?\n.*?(\d{2}-\d{4})"
    pola_nama = r"NAMA\s*:\s*([^\n]+)"
    pola_dokumen = r"Nomor Dokumen\s*:\s*(\S+)"
    
    match_masa = re.search(pola_masa, text, re.DOTALL)
    match_nama = re.search(pola_nama, text)
    match_dokumen = re.search(pola_dokumen, text)
    
    if match_masa and match_nama and match_dokumen:
        masa_pajak = match_masa.group(1)
        nama_wp = clean_filename(match_nama.group(1).strip())
        nomor_dokumen = match_dokumen.group(1).strip().replace('/', '-')
        return f"{masa_pajak} - {nama_wp} - {nomor_dokumen}.pdf"
    return None

def try_billing_pattern(text):
    """Mencoba pola dari billing.py."""
    kode_billing_match = re.search(r"KODE BILLING\s*[:：]\s*(\d+)", text)
    nama_match = re.search(r"NAMA\s*[:：]\s*(.*?)\s*(?:\n|$)", text)
    masa_pajak_match = re.search(r"\b\d{6}-\d{3}\s+(\d{8})\b", text)

    if kode_billing_match and nama_match and masa_pajak_match:
        kode_billing = kode_billing_match.group(1).strip()
        nama = nama_match.group(1).strip()
        masa_pajak = masa_pajak_match.group(1).strip()
        unifikasi_part = "-Unifikasi" if re.search(r"\b41112\d*-\d+\b", text) else ""
        
        new_name_raw = f"{kode_billing}-{nama}{unifikasi_part}-{masa_pajak}.pdf"
        return clean_filename(new_name_raw)
    return None
    
def try_faktur2_indomarco_pattern(text):
    """Mencoba pola dari faktur2.py (khusus Indomarco)."""
    referensi_match = re.search(r"Perj*[:：]\s*(.*?)\s*(?:\n|$)", text)
    if referensi_match:
        pattern_nama = r"Pengusaha Kena Pajak:\s*\nNama\s*[:：]\s*(.*?)\s*(?:\n|$)"
        nama_match = re.search(pattern_nama, text)
        if nama_match:
            referensi = clean_filename(referensi_match.group(1).strip())
            nama = nama_match.group(1).strip()
            return f"{referensi} {nama}.pdf"
    return None

def try_bukti_tf_pattern(text):
    """Mencoba pola dari buktiTF.py."""
    nama_penerima, nominal_transfer, tanggal_setuju = None, None, None
    for baris in text.split('\n'):
        if "Rekening Tujuan" in baris and "/" in baris:
            try:
                nama_penerima = baris.split('/')[1].replace('(Rp)', '').strip()
                break
            except IndexError: continue
    
    pola_nominal = r"Jumlah\s*:\s*(Rp\s*[\d,]+\.\d{2})"
    cocok_nominal = re.search(pola_nominal, text)
    if cocok_nominal:
        nominal_transfer = re.sub(r'\s+', ' ', cocok_nominal.group(1).strip())
    
    pola_tanggal = r"Disetujui\s+(\d{2}/\d{2}/\d{4})"
    cocok_tanggal = re.search(pola_tanggal, text)
    if cocok_tanggal:
        tanggal_setuju = cocok_tanggal.group(1).replace('/', '-')

    if nama_penerima and nominal_transfer and tanggal_setuju:
        nama_penerima_clean = clean_filename(nama_penerima)
        return f"{nama_penerima_clean} - {nominal_transfer} - {tanggal_setuju}.pdf".replace(',', '.')
    return None

BUILT_IN_TEMPLATES = {
    "📄 Faktur (Referensi & Nama Pembeli)": try_faktur_pattern,
    "📄 Faktur Masukan (Nama PKP & Referensi)": try_faktur_masukan_pattern,
    "📄 Faktur Penjualan (No. Faktur)": try_faktur_penjualan_pattern,
    "📄 Faktur Indomarco": try_faktur2_indomarco_pattern,
    "🧾 Bukti Potong Pajak": try_bukti_potong_pattern,
    "💳 Kode Billing Pajak": try_billing_pattern,
    "💸 Bukti Transfer": try_bukti_tf_pattern
}

def run_universal_extraction(text, template_name):
    """
    Menjalankan fungsi ekstraksi yang sesuai dengan nama template bawaan.
    """
    if template_name in BUILT_IN_TEMPLATES:
        extractor_func = BUILT_IN_TEMPLATES[template_name]
        return extractor_func(text)
    return None