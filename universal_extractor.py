import re

def clean_filename(name):
    """
    Satu fungsi untuk membersihkan semua karakter ilegal dari sebuah string
    yang akan digunakan sebagai nama file.
    """
    if not isinstance(name, str):
        name = str(name)
    name = name.replace('/', '-')
    return re.sub(r'[\\*?:"<>|]', '', name).strip()


def try_faktur_pattern(text):
    """Pola Faktur Pembeli yang paling andal."""
    buyer_block_match = re.search(r"Pembeli Barang Kena Pajak.*?(Alamat|NPWP)", text, re.DOTALL)
    if buyer_block_match:
        buyer_block_text = buyer_block_match.group(0)
        nama_match = re.search(r"Nama\s*[:：]\s*(.*?)\s*(?:\n|$)", buyer_block_text)
        if nama_match:
            referensi_match = re.search(r"\(Referensi:\s*(.*?)\)", text)
            if referensi_match:
                referensi = clean_filename(referensi_match.group(1))
                nama = clean_filename(nama_match.group(1))
                if not re.match(r"\d{2}\.\d{3}", nama):
                    return f"{referensi} {nama}.pdf"
    return None

def try_faktur_masukan_pattern(text):
    """Pola Faktur Masukan/Pengusaha yang paling andal."""
    pkp_block_match = re.search(r"Pengusaha Kena Pajak.*?(Alamat|NPWP)", text, re.DOTALL)
    if pkp_block_match:
        pkp_block_text = pkp_block_match.group(0)
        nama_match = re.search(r"Nama\s*[:：]\s*(.*?)\s*(?:\n|$)", pkp_block_text)
        if nama_match:
            referensi_match = re.search(r"\(Referensi:\s*([^)]+)\)", text)
            if referensi_match:
                referensi = clean_filename(referensi_match.group(1))
                nama = clean_filename(nama_match.group(1))
                if not re.match(r"\d{2}\.\d{3}", nama):
                    return f"{nama} {referensi}.pdf"
    return None
    
def try_faktur2_indomarco_pattern(text):
    """Pola Faktur Indomarco yang paling andal."""
    pkp_block_match = re.search(r"Pengusaha Kena Pajak.*?(Alamat|NPWP)", text, re.DOTALL)
    if pkp_block_match:
        pkp_block_text = pkp_block_match.group(0)
        nama_match = re.search(r"Nama\s*[:：]\s*(.*?)\s*(?:\n|$)", pkp_block_text)
        if nama_match:
            referensi_match = re.search(r"Perj*[:：]\s*(.*?)\s*(?:\n|$)", text)
            if referensi_match:
                referensi = clean_filename(referensi_match.group(1))
                nama = clean_filename(nama_match.group(1))
                if not re.match(r"\d{2}\.\d{3}", nama):
                    return f"{referensi} {nama}.pdf"
    return None

def try_faktur_penjualan_pattern(text):
    pola = r"No\.\s*Faktur\s*[:：]\s*(\S+)"
    match = re.search(pola, text)
    if match:
        referensi = clean_filename(match.group(1))
        return f"No Faktur - {referensi}.pdf"
    return None

def try_bukti_potong_pattern(text):
    pola_masa = r"MASA PAJAK.*?\n.*?(\d{2}-\d{4})"
    pola_nama = r"NAMA\s*:\s*([^\n]+)"
    pola_dokumen = r"Nomor Dokumen\s*:\s*(\S+)"
    match_masa = re.search(pola_masa, text, re.DOTALL)
    match_nama = re.search(pola_nama, text)
    match_dokumen = re.search(pola_dokumen, text)
    if match_masa and match_nama and match_dokumen:
        masa_pajak = clean_filename(match_masa.group(1))
        nama_wp = clean_filename(match_nama.group(1))
        nomor_dokumen = clean_filename(match_dokumen.group(1))
        return f"{masa_pajak} - {nama_wp} - {nomor_dokumen}.pdf"
    return None

def try_billing_pattern(text):
    kode_billing_match = re.search(r"KODE BILLING\s*[:：]\s*(\d+)", text)
    nama_match = re.search(r"NAMA\s*[:：]\s*(.*?)\s*(?:\n|$)", text)
    masa_pajak_match = re.search(r"\b\d{6}-\d{3}\s+(\d{8})\b", text)
    if kode_billing_match and nama_match and masa_pajak_match:
        kode_billing = clean_filename(kode_billing_match.group(1))
        nama = clean_filename(nama_match.group(1))
        masa_pajak = clean_filename(masa_pajak_match.group(1))
        unifikasi_part = "-Unifikasi" if re.search(r"\b41112\d*-\d+\b", text) else ""
        return f"{kode_billing}-{nama}{unifikasi_part}-{masa_pajak}.pdf"
    return None

def try_bukti_tf_pattern(text):
    nama_penerima, nominal_transfer, tanggal_setuju = None, None, None
    for baris in text.split('\n'):
        if "Rekening Tujuan" in baris and "/" in baris:
            try:
                nama_penerima = baris.split('/')[1].replace('(Rp)', '')
                break
            except IndexError: continue
    pola_nominal = r"Jumlah\s*:\s*(Rp\s*[\d,]+\.\d{2})"
    cocok_nominal = re.search(pola_nominal, text)
    if cocok_nominal:
        nominal_transfer = re.sub(r'\s+', ' ', cocok_nominal.group(1))
    pola_tanggal = r"Disetujui\s+(\d{2}/\d{2}/\d{4})"
    cocok_tanggal = re.search(pola_tanggal, text)
    if cocok_tanggal:
        tanggal_setuju = cocok_tanggal.group(1)
    if nama_penerima and nominal_transfer and tanggal_setuju:
        nama_penerima_clean = clean_filename(nama_penerima)
        tanggal_setuju_clean = clean_filename(tanggal_setuju)
        return f"{nama_penerima_clean} - {nominal_transfer} - {tanggal_setuju_clean}.pdf".replace(',', '.')
    return None

BUILT_IN_TEMPLATES = {
    "📄 Faktur Pajak Keluaran": try_faktur_pattern,
    "📄 Faktur Pajak Masukan": try_faktur_masukan_pattern,
    "📄 Faktur Penjualan": try_faktur_penjualan_pattern,
    "📄 Faktur Pajak Indomarco": try_faktur2_indomarco_pattern,
    "🧾 Bukti Potong Pajak": try_bukti_potong_pattern,
    "💳 Kode Billing Pajak": try_billing_pattern,
    "💸 Bukti Transfer": try_bukti_tf_pattern
}

def run_universal_extraction(text, template_name):
    if template_name in BUILT_IN_TEMPLATES:
        extractor_func = BUILT_IN_TEMPLATES[template_name]
        return extractor_func(text)
    return None