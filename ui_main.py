from PyQt5.QtWidgets import QMainWindow, QPushButton, QFileDialog, QLineEdit, QTextEdit, QProgressBar, QLabel
from PyQt5.QtCore import Qt
from pdf_tools import process_pdfs
from zip_tools import save_zip
from utils import validate_regex

class PDFRenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Renamer Pro")
        self.resize(600, 400)

        # Input pattern
        self.pattern_input = QLineEdit(self)
        self.pattern_input.setPlaceholderText("Masukkan regex pattern...")
        self.pattern_input.setGeometry(20, 20, 400, 30)

        # Tombol pilih file
        self.select_btn = QPushButton("Pilih PDF", self)
        self.select_btn.setGeometry(440, 20, 120, 30)
        self.select_btn.clicked.connect(self.select_files)

        # Tombol proses
        self.process_btn = QPushButton("Proses", self)
        self.process_btn.setGeometry(20, 60, 120, 30)
        self.process_btn.clicked.connect(self.process_files)

        # Log
        self.log_area = QTextEdit(self)
        self.log_area.setGeometry(20, 100, 560, 200)
        self.log_area.setReadOnly(True)

        # Progress
        self.progress = QProgressBar(self)
        self.progress.setGeometry(20, 320, 560, 25)

        self.selected_files = []

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih File PDF", "", "PDF Files (*.pdf)")
        if files:
            self.selected_files = files
            self.log_area.append(f"{len(files)} file dipilih.")

    def process_files(self):
        pattern = self.pattern_input.text().strip()
        if not validate_regex(pattern):
            self.log_area.append("❌ Regex tidak valid.")
            return
        if not self.selected_files:
            self.log_area.append("❌ Tidak ada file dipilih.")
            return

        self.log_area.append("Memproses file...")
        renamed_files = process_pdfs(self.selected_files, pattern, self.progress, self.log_area)

        if renamed_files:
            save_path, _ = QFileDialog.getSaveFileName(self, "Simpan Zip", "", "Zip Files (*.zip)")
            if save_path:
                save_zip(renamed_files, save_path)
                self.log_area.append(f"✅ Zip disimpan di: {save_path}")
