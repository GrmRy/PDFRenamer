import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QLabel, QFileDialog, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
    QMessageBox, QComboBox, QTextEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
from pathlib import Path

from pdf_tools import extract_pdf_fields, process_single_pdf
from utils import load_templates, save_templates
from zip_tools import save_zip, ZipError

# --- Worker Thread untuk Proses Massal ---
class BulkProcessWorker(QThread):
    """Worker thread untuk menangani proses rename massal di latar belakang."""
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(str) # Mengirim path file ZIP jika berhasil
    error = pyqtSignal(str)

    def __init__(self, uploaded_files, template, save_path):
        super().__init__()
        self.uploaded_files = uploaded_files
        self.template = template
        self.save_path = save_path
        self.is_running = True

    def run(self):
        try:
            self.log.emit(f"🚀 Memulai proses untuk {len(self.uploaded_files)} file...")
            renamed_data = {}
            skipped_files = []
            total = len(self.uploaded_files)

            for i, file_path in enumerate(self.uploaded_files):
                if not self.is_running:
                    self.log.emit("Proses dibatalkan oleh pengguna.")
                    return

                new_name, original_content = process_single_pdf(file_path, self.template)
                if new_name:
                    renamed_data[new_name] = original_content
                    self.log.emit(f"✅ Berhasil memproses: {file_path}")
                else:
                    skipped_files.append(file_path)
                    self.log.emit(f"⚠️ Dilewati: {file_path} (tidak semua field ditemukan)")

                self.progress.emit(int((i + 1) / total * 100))

            if not renamed_data:
                self.error.emit("Tidak ada file yang berhasil diproses.")
                return

            self.log.emit("📦 Membuat file ZIP...")
            save_zip(renamed_data, self.save_path)

            if skipped_files:
                self.log.emit("\n--- Ringkasan ---")
                self.log.emit(f"⚠️ {len(skipped_files)} file dilewati karena tidak cocok dengan template.")

            self.finished.emit(self.save_path)

        except ZipError as e:
            self.error.emit(f"Gagal membuat ZIP: {e}")
        except Exception as e:
            self.error.emit(f"Terjadi kesalahan tak terduga: {e}")

    def stop(self):
        self.is_running = False

# --- Jendela Aplikasi Utama ---
class PDFRenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Renamer Pro (Desktop Edition)")
        self.setGeometry(100, 100, 800, 600)
        self.templates = load_templates()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        # Layout utama
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Sidebar Navigasi
        nav_layout = QVBoxLayout()
        nav_layout.setSpacing(10)

        self.btn_dashboard = QPushButton("🏠 Dashboard")
        self.btn_manager = QPushButton("🛠️ Manajer Template")
        self.btn_process = QPushButton("⚙️ Proses Massal")

        nav_layout.addWidget(self.btn_dashboard)
        nav_layout.addWidget(self.btn_manager)
        nav_layout.addWidget(self.btn_process)
        nav_layout.addStretch()

        # Halaman (Stacked Widget)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.create_dashboard_page())
        self.pages.addWidget(self.create_manager_page())
        self.pages.addWidget(self.create_process_page())

        main_layout.addLayout(nav_layout, 1)
        main_layout.addWidget(self.pages, 4)

        # Koneksi Sinyal
        self.btn_dashboard.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.btn_manager.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        self.btn_process.clicked.connect(lambda: self.pages.setCurrentIndex(2))

        self.update_manager_combo()
        self.update_process_combo()

    # --- Halaman 1: Dashboard ---
    def create_dashboard_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        title = QLabel("Selamat Datang di PDF Renamer Pro!")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)

        desc = QLabel("Aplikasi ini dirancang untuk menyederhanakan tugas paling membosankan: me-rename file PDF satu per satu.\nDengan membuat 'template', Anda bisa me-rename ratusan file sesuai format yang Anda inginkan hanya dengan beberapa klik.")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        stats_title = QLabel("Statistik Anda")
        stats_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(stats_title)
        
        self.stats_label = QLabel(f"Jumlah Template Tersimpan: {len(self.templates)} Template")
        layout.addWidget(self.stats_label)

        info_title = QLabel("Mulai dari mana?")
        info_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(info_title)
        
        info = QLabel("1. Buka <b>🛠️ Manajer Template</b> untuk membuat pola rename pertama Anda.\n2. Setelah template disimpan, buka <b>⚙️ Proses Massal</b> untuk menggunakannya.")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        layout.addStretch()
        return widget

    # --- Halaman 2: Manajer Template ---
    def create_manager_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Pilihan Template
        top_layout = QHBoxLayout()
        self.manager_combo = QComboBox()
        self.manager_template_name = QLineEdit()
        self.manager_template_name.setPlaceholderText("Nama Template Baru atau yang Diedit")
        top_layout.addWidget(QLabel("Pilih/Edit Template:"))
        top_layout.addWidget(self.manager_combo)
        top_layout.addWidget(self.manager_template_name)
        layout.addLayout(top_layout)

        # Upload & Deteksi
        self.manager_upload_btn = QPushButton("Unggah PDF Contoh untuk Deteksi Field")
        layout.addWidget(self.manager_upload_btn)
        self.manager_detected_fields_list = QListWidget()
        layout.addWidget(QLabel("Field yang Ditemukan (Centang untuk Digunakan):"))
        layout.addWidget(self.manager_detected_fields_list)

        # Aturan & Urutan
        order_layout = QHBoxLayout()
        self.manager_rules_list = QListWidget()
        self.manager_rules_list.setDragDropMode(QListWidget.InternalMove) # Drag n Drop!
        order_layout.addWidget(QLabel("Susun Urutan Nama File (Drag & Drop):"))
        order_layout.addWidget(self.manager_rules_list)
        layout.addLayout(order_layout)
        
        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.manager_save_btn = QPushButton("💾 Simpan Template")
        self.manager_delete_btn = QPushButton("🗑️ Hapus Template")
        btn_layout.addWidget(self.manager_save_btn)
        btn_layout.addWidget(self.manager_delete_btn)
        layout.addLayout(btn_layout)

        # Koneksi sinyal
        self.manager_upload_btn.clicked.connect(self.detect_fields_from_sample)
        self.manager_combo.currentTextChanged.connect(self.load_template_for_editing)
        self.manager_detected_fields_list.itemChanged.connect(self.update_rules_from_checkbox)
        self.manager_save_btn.clicked.connect(self.save_template)
        self.manager_delete_btn.clicked.connect(self.delete_template)

        return widget

    # --- Halaman 3: Proses Massal ---
    def create_process_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Pilihan Template
        layout.addWidget(QLabel("Langkah 1: Pilih Template yang akan digunakan:"))
        self.process_combo = QComboBox()
        layout.addWidget(self.process_combo)
        self.process_format_label = QLabel("Format Nama File: ")
        layout.addWidget(self.process_format_label)

        # Upload Massal
        layout.addWidget(QLabel("Langkah 2: Pilih semua file PDF yang ingin di-rename:"))
        self.process_upload_btn = QPushButton("Pilih File PDF...")
        layout.addWidget(self.process_upload_btn)
        self.process_file_list = QListWidget()
        layout.addWidget(self.process_file_list)

        # Proses & Log
        layout.addWidget(QLabel("Langkah 3: Proses dan Unduh Hasil"))
        self.process_run_btn = QPushButton("PROSES & BUAT FILE ZIP")
        layout.addWidget(self.process_run_btn)
        self.process_log = QTextEdit()
        self.process_log.setReadOnly(True)
        layout.addWidget(QLabel("Log Proses:"))
        layout.addWidget(self.process_log)
        self.process_progress = QProgressBar()
        layout.addWidget(self.process_progress)
        
        # Koneksi Sinyal
        self.process_combo.currentTextChanged.connect(self.update_process_format_label)
        self.process_upload_btn.clicked.connect(self.select_bulk_files)
        self.process_run_btn.clicked.connect(self.run_bulk_process)

        return widget

    # --- Logika & Fungsi Bantuan ---
    
    # Fungsi untuk Manajer Template
    def update_manager_combo(self):
        self.manager_combo.blockSignals(True)
        self.manager_combo.clear()
        self.manager_combo.addItem("-- Buat Baru --")
        self.manager_combo.addItems(sorted(self.templates.keys()))
        self.manager_combo.blockSignals(False)

    def load_template_for_editing(self, template_name):
        self.manager_detected_fields_list.clear()
        self.manager_rules_list.clear()
        
        if template_name and template_name != "-- Buat Baru --":
            self.manager_template_name.setText(template_name)
            rules = self.templates.get(template_name, {}).get("aturan", [])
            for rule in rules:
                self.manager_rules_list.addItem(rule)
        else:
            self.manager_template_name.clear()

    def detect_fields_from_sample(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih PDF Contoh", "", "PDF Files (*.pdf)")
        if not file_path:
            return

        self.manager_detected_fields_list.clear()
        self.manager_rules_list.clear()

        fields = extract_pdf_fields(file_path)
        if not fields:
            QMessageBox.warning(self, "Gagal", "Tidak ada field yang dapat dideteksi dari file ini.")
            return
            
        for key, value in fields.items():
            item = QListWidgetItem(f"{key}: {value}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.manager_detected_fields_list.addItem(item)

    def update_rules_from_checkbox(self, item):
        field_name = item.text().split(":")[0]
        if item.checkState() == Qt.Checked:
            # Hindari duplikat
            if not self.manager_rules_list.findItems(field_name, Qt.MatchExactly):
                self.manager_rules_list.addItem(field_name)
        else:
            items_to_remove = self.manager_rules_list.findItems(field_name, Qt.MatchExactly)
            for item_to_remove in items_to_remove:
                self.manager_rules_list.takeItem(self.manager_rules_list.row(item_to_remove))

    def save_template(self):
        template_name = self.manager_template_name.text().strip()
        if not template_name:
            QMessageBox.critical(self, "Error", "Nama template tidak boleh kosong.")
            return

        rules = [self.manager_rules_list.item(i).text() for i in range(self.manager_rules_list.count())]
        if not rules:
            QMessageBox.critical(self, "Error", "Template harus memiliki minimal satu aturan/field.")
            return

        self.templates[template_name] = {"aturan": rules, "pemisah": " - "}
        save_templates(self.templates)
        QMessageBox.information(self, "Sukses", f"Template '{template_name}' berhasil disimpan.")
        
        self.update_all_combos()
        self.manager_combo.setCurrentText(template_name)
        self.stats_label.setText(f"Jumlah Template Tersimpan: {len(self.templates)} Template")


    def delete_template(self):
        template_name = self.manager_combo.currentText()
        if not template_name or template_name == "-- Buat Baru --":
            QMessageBox.critical(self, "Error", "Pilih template yang valid untuk dihapus.")
            return

        reply = QMessageBox.question(self, "Konfirmasi", f"Anda yakin ingin menghapus template '{template_name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if template_name in self.templates:
                del self.templates[template_name]
                save_templates(self.templates)
                QMessageBox.information(self, "Sukses", f"Template '{template_name}' telah dihapus.")
                self.manager_template_name.clear()
                self.manager_rules_list.clear()
                self.manager_detected_fields_list.clear()
                self.update_all_combos()
                self.stats_label.setText(f"Jumlah Template Tersimpan: {len(self.templates)} Template")


    # Fungsi untuk Proses Massal
    def update_process_combo(self):
        self.process_combo.blockSignals(True)
        self.process_combo.clear()
        self.process_combo.addItems(sorted(self.templates.keys()))
        self.process_combo.blockSignals(False)
        self.update_process_format_label(self.process_combo.currentText())

    def update_process_format_label(self, template_name):
        if template_name in self.templates:
            template = self.templates[template_name]
            separator = template.get("pemisah", " - ")
            format_str = separator.join(template.get("aturan", []))
            self.process_format_label.setText(f"<b>Format Nama File:</b> {format_str}")
        else:
            self.process_format_label.setText("<b>Format Nama File:</b> Pilih template terlebih dahulu.")

    def select_bulk_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih File PDF untuk Diproses", "", "PDF Files (*.pdf)")
        if files:
            self.uploaded_files = files
            self.process_file_list.clear()
            self.process_file_list.addItems([Path(f).name for f in files])
            self.process_log.append(f"✅ {len(files)} file dipilih untuk diproses.")

    def run_bulk_process(self):
        template_name = self.process_combo.currentText()
        if not template_name:
            QMessageBox.critical(self, "Error", "Pilih sebuah template terlebih dahulu.")
            return
            
        if not hasattr(self, 'uploaded_files') or not self.uploaded_files:
            QMessageBox.critical(self, "Error", "Pilih file PDF yang akan diproses.")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Simpan Hasil ke File ZIP", f"Hasil Rename ({template_name}).zip", "Zip Files (*.zip)")
        if not save_path:
            return

        self.process_run_btn.setEnabled(False)
        self.process_log.clear()
        
        template = self.templates[template_name]
        self.worker = BulkProcessWorker(self.uploaded_files, template, save_path)
        self.worker.log.connect(self.process_log.append)
        self.worker.progress.connect(self.process_progress.setValue)
        self.worker.finished.connect(self.on_bulk_process_finished)
        self.worker.error.connect(self.on_bulk_process_error)
        self.worker.start()

    def on_bulk_process_finished(self, save_path):
        self.process_log.append(f"\n🎉🎉🎉\nProses selesai! File ZIP disimpan di: {save_path}")
        QMessageBox.information(self, "Sukses", f"Proses selesai! File ZIP telah disimpan.")
        self.process_run_btn.setEnabled(True)
        self.worker = None

    def on_bulk_process_error(self, message):
        self.process_log.append(f"\n💥 ERROR: {message}")
        QMessageBox.critical(self, "Error", f"Terjadi kesalahan selama proses:\n{message}")
        self.process_run_btn.setEnabled(True)
        self.worker = None

    def update_all_combos(self):
        self.update_manager_combo()
        self.update_process_combo()
        
    def closeEvent(self, event):
        """Memastikan thread berhenti saat aplikasi ditutup."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait() # Tunggu hingga thread benar-benar berhenti
        event.accept()