import sys
import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QLabel, QFileDialog, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
    QMessageBox, QComboBox, QTextEdit, QGroupBox, QScrollArea)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
from pathlib import Path
import logging
import datetime

from pdf_tools import (extract_pdf_fields, process_single_pdf, validate_pdf_file, 
                      validate_template_name, FileValidationError, PDFProcessingError)
from utils import (load_templates, save_templates, TemplateError, ConfigError,
                   load_config, save_config)
from zip_tools import save_zip, ZipError, ZipValidationError
from universal_extractor import BUILT_IN_TEMPLATES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('pdf_renamer.log'), logging.StreamHandler()]
)

class BulkProcessWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, bool, str)
    finished = pyqtSignal(str, int, int)
    error = pyqtSignal(str)

    def __init__(self, uploaded_files, template, save_path):
        super().__init__()
        self.uploaded_files = uploaded_files
        self.template = template
        self.save_path = save_path
        self.template_name = ""
        self.is_running = True
        self.success_count = 0
        self.error_count = 0

    def run(self):
        total_files = len(self.uploaded_files)
        renamed_data = {}
        self.log.emit(f"🚀 Memulai proses untuk {total_files} file dengan template '{self.template_name}'...")
        
        for i, file_path in enumerate(self.uploaded_files):
            if not self.is_running:
                self.log.emit("❌ Proses dibatalkan oleh pengguna.")
                return
            
            try:
                new_name, original_content, error_msg = process_single_pdf(
                    file_path, self.template, self.template_name
                )
                
                if new_name and original_content:
                    counter = 1
                    original_new_name = new_name
                    while new_name in renamed_data:
                        name_part, ext = original_new_name.rsplit('.', 1)
                        new_name = f"{name_part}_{counter}.{ext}"
                        counter += 1
                    
                    renamed_data[new_name] = original_content
                    self.success_count += 1
                    self.log.emit(f"✅ [{i+1}/{total_files}] {Path(file_path).name} → {new_name}")
                else:
                    self.error_count += 1
                    error_message = error_msg or "Gagal memproses file"
                    self.log.emit(f"❌ [{i+1}/{total_files}] {Path(file_path).name}: {error_message}")
            
            except Exception as e:
                self.error_count += 1
                self.log.emit(f"💥 [{i+1}/{total_files}] {Path(file_path).name}: Error tak terduga: {e}")
            
            progress_percent = int((i + 1) / total_files * 90)
            self.progress.emit(progress_percent)
        
        self.log.emit(f"\n📊 Ringkasan: ✅ Berhasil: {self.success_count} | ❌ Gagal: {self.error_count}")
        
        if not renamed_data:
            self.error.emit("Tidak ada file yang berhasil diproses.")
            return
        
        try:
            self.log.emit(f"\n📦 Membuat file ZIP...")
            save_zip(renamed_data, self.save_path)
            self.progress.emit(100)
            self.finished.emit(self.save_path, self.success_count, total_files)
        except (ZipError, ZipValidationError, Exception) as e:
            self.error.emit(f"Gagal membuat ZIP: {e}")

    def stop(self):
        self.is_running = False

class ValidationUtils:
    @staticmethod
    def show_message(parent, title, message, icon=QMessageBox.Information):
        msg_box = QMessageBox(parent)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

class PDFRenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Renamer Pro")
        self.setGeometry(100, 100, 1100, 750)
        
        self.config = load_config()
        self.default_save_path = self.config.get("default_save_path", "")
        
        try:
            self.templates = load_templates()
        except ConfigError as e:
            ValidationUtils.show_message(self, "Error Konfigurasi", f"Gagal memuat template: {e}", QMessageBox.Critical)
            self.templates = {}
        
        self.built_in_templates = list(BUILT_IN_TEMPLATES.keys())
        self.worker = None
        self.uploaded_files = []
        
        self.init_ui()
        self.apply_stylesheet()
        
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        nav_widget = self.create_nav_widget()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.create_dashboard_page())
        self.pages.addWidget(self.create_manager_page())
        self.pages.addWidget(self.create_process_page())
        self.pages.addWidget(self.create_settings_page()) # Halaman baru
        
        main_layout.addWidget(nav_widget)
        main_layout.addWidget(self.pages, 1)
        self.update_all_combos()

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
            }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #c0c0c0;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton#NavButton {
                text-align: left;
                background-color: #f8f8f8;
            }
            QPushButton#RunButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            QPushButton#RunButton:hover {
                background-color: #45a049;
            }
            QPushButton#StopButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
            }
            QPushButton#StopButton:hover {
                background-color: #da190b;
            }
            QLineEdit, QComboBox, QListWidget, QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }
        """)

    def create_nav_widget(self):
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_widget.setMaximumWidth(220)
        
        buttons = {
            "🏠 Dashboard": 0, "🛠️ Manajer Template": 1,
            "⚙️ Proses Massal": 2, "⚙️ Pengaturan": 3
        }
        for text, index in buttons.items():
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.clicked.connect(lambda _, i=index: self.pages.setCurrentIndex(i))
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        return nav_widget

    def create_dashboard_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        title = QLabel("Selamat Datang di PDF Renamer!")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        layout.addWidget(title)

        self.stats_label = QLabel()
        self.update_stats_label()
        layout.addWidget(self.stats_label)

        guide_group = QGroupBox("Panduan Cepat")
        guide_layout = QVBoxLayout(guide_group)
        steps = [
            "1. Buka <b>Manajer Template</b> untuk membuat template baru atau pilih template bawaan.",
            "2. Untuk template baru, unggah contoh PDF untuk mendeteksi field.",
            "3. Centang field yang diinginkan dan susun urutannya.",
            "4. Simpan template kustom Anda.",
            "5. Buka <b>Proses Massal</b>, pilih template, dan unggah file PDF Anda.",
            "6. Klik 'Mulai Proses' dan unduh hasilnya dalam format ZIP."
        ]
        for step in steps:
            guide_layout.addWidget(QLabel(step))
        layout.addWidget(guide_group)
        layout.addStretch()
        return widget

    def create_manager_page(self):
        scroll_area = QScrollArea()
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group1 = QGroupBox("Pilih atau Buat Template")
        layout1 = QVBoxLayout(group1)
        self.manager_combo = QComboBox()
        self.manager_combo.currentTextChanged.connect(self.load_template_for_editing)
        layout1.addWidget(self.manager_combo)
        layout1.addWidget(QLabel("Nama Template Kustom:"))
        self.manager_template_name = QLineEdit()
        self.manager_template_name.setPlaceholderText("Hanya diisi untuk template baru/diedit")
        layout1.addWidget(self.manager_template_name)
        layout.addWidget(group1)

        self.custom_template_group = QGroupBox("Desain Template Kustom")
        layout2 = QVBoxLayout(self.custom_template_group)
        self.manager_upload_btn = QPushButton("📄 Unggah PDF Contoh untuk Deteksi Field")
        self.manager_upload_btn.clicked.connect(self.detect_fields_from_sample)
        layout2.addWidget(self.manager_upload_btn)
        layout2.addWidget(QLabel("Field Ditemukan (Centang untuk digunakan):"))
        self.manager_detected_fields_list = QListWidget()
        self.manager_detected_fields_list.itemChanged.connect(self.update_rules_from_checkbox)
        layout2.addWidget(self.manager_detected_fields_list)
        layout2.addWidget(QLabel("Urutan Field (Drag & Drop untuk mengubah):"))
        self.manager_rules_list = QListWidget()
        self.manager_rules_list.setDragDropMode(QListWidget.InternalMove)
        layout2.addWidget(self.manager_rules_list)
        separator_layout = QHBoxLayout()
        separator_layout.addWidget(QLabel("Pemisah:"))
        self.manager_separator_input = QLineEdit(" - ")
        separator_layout.addWidget(self.manager_separator_input)
        layout2.addLayout(separator_layout)
        layout.addWidget(self.custom_template_group)

        btn_layout = QHBoxLayout()
        self.manager_save_btn = QPushButton("💾 Simpan Template Kustom")
        self.manager_delete_btn = QPushButton("🗑️ Hapus Template Kustom")
        self.manager_save_btn.clicked.connect(self.save_template)
        self.manager_delete_btn.clicked.connect(self.delete_template)
        btn_layout.addWidget(self.manager_save_btn)
        btn_layout.addWidget(self.manager_delete_btn)
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        return scroll_area

    def create_process_page(self):
        scroll_area = QScrollArea()
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Grup 1: Pengaturan
        group1 = QGroupBox("Langkah 1: Pengaturan Proses")
        layout1 = QVBoxLayout(group1)
        layout1.addWidget(QLabel("Pilih Template:"))
        self.process_combo = QComboBox()
        self.process_combo.currentTextChanged.connect(self.update_process_format_label)
        layout1.addWidget(self.process_combo)
        self.process_format_label = QLabel("Format: ")
        layout1.addWidget(self.process_format_label)
        layout.addWidget(group1)

        # Grup 2: File
        group2 = QGroupBox("Langkah 2: Pilih File PDF")
        layout2 = QVBoxLayout(group2)
        btn_upload_layout = QHBoxLayout()
        self.process_upload_btn = QPushButton("📁 Pilih File...")
        self.process_clear_btn = QPushButton("🗑️ Hapus Daftar")
        self.process_upload_btn.clicked.connect(self.select_bulk_files)
        self.process_clear_btn.clicked.connect(self.clear_selected_files)
        btn_upload_layout.addWidget(self.process_upload_btn)
        btn_upload_layout.addWidget(self.process_clear_btn)
        layout2.addLayout(btn_upload_layout)
        self.process_file_list = QListWidget()
        layout2.addWidget(self.process_file_list)
        layout.addWidget(group2)

        # Grup 3: Eksekusi
        group3 = QGroupBox("Langkah 3: Jalankan dan Pantau Proses")
        layout3 = QVBoxLayout(group3)
        btn_process_layout = QHBoxLayout()
        self.process_run_btn = QPushButton("🚀 MULAI PROSES")
        self.process_run_btn.setObjectName("RunButton")
        self.process_stop_btn = QPushButton("⏹️ STOP")
        self.process_stop_btn.setObjectName("StopButton")
        self.process_run_btn.clicked.connect(self.run_bulk_process)
        self.process_stop_btn.clicked.connect(self.stop_bulk_process)
        self.process_stop_btn.setEnabled(False)
        btn_process_layout.addWidget(self.process_run_btn)
        btn_process_layout.addWidget(self.process_stop_btn)
        layout3.addLayout(btn_process_layout)
        self.process_progress = QProgressBar()
        layout3.addWidget(self.process_progress)
        layout3.addWidget(QLabel("Log Proses:"))
        self.process_log = QTextEdit()
        self.process_log.setReadOnly(True)
        layout3.addWidget(self.process_log)
        layout.addWidget(group3)

        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        return scroll_area
    
    def create_settings_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)

        save_group = QGroupBox("Lokasi Penyimpanan Default")
        save_layout = QVBoxLayout(save_group)
        
        save_info_label = QLabel("Atur folder default untuk menyimpan hasil file ZIP.")
        save_layout.addWidget(save_info_label)
        
        path_layout = QHBoxLayout()
        self.default_save_path_edit = QLineEdit(self.default_save_path)
        self.default_save_path_edit.setPlaceholderText("Belum ada folder default yang diatur")
        self.default_save_path_edit.setReadOnly(True)
        path_layout.addWidget(self.default_save_path_edit)
        
        browse_btn = QPushButton("Pilih Folder...")
        browse_btn.clicked.connect(self.set_default_save_location) # Hubungkan ke fungsi
        path_layout.addWidget(browse_btn)
        save_layout.addLayout(path_layout)
        layout.addWidget(save_group)
        
        layout.addStretch()
        return widget
    
    def set_default_save_location(self):
        """Membuka dialog untuk memilih folder dan menyimpannya."""
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Penyimpanan Default", self.default_save_path)
        if folder:
            self.default_save_path = folder
            self.default_save_path_edit.setText(self.default_save_path)
            self.config["default_save_path"] = self.default_save_path
            try:
                save_config(self.config)
                ValidationUtils.show_message(self, "Sukses", "Lokasi penyimpanan default berhasil disimpan.")
            except ConfigError as e:
                ValidationUtils.show_message(self, "Error", f"Gagal menyimpan pengaturan: {e}", QMessageBox.Critical)

    def run_bulk_process(self):
        current_text = self.process_combo.currentText()
        template_name = current_text.replace("⚙️ ", "").strip()
        
        if not self.uploaded_files:
            ValidationUtils.show_message(self, "File Belum Dipilih", "Pilih file PDF yang akan diproses.", QMessageBox.Warning)
            return

        template_to_use = {}
        if template_name in self.templates:
            template_to_use = self.templates[template_name]
        elif template_name not in self.built_in_templates:
            ValidationUtils.show_message(self, "Template Tidak Valid", "Silakan pilih template yang valid.", QMessageBox.Warning)
            return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")    
        default_filename = os.path.join(self.default_save_path, f"Hasil Rename ({template_name})({timestamp}).zip")
        save_path, _ = QFileDialog.getSaveFileName(self, "Simpan Hasil ke ZIP", default_filename, "Zip Files (*.zip)")
        
        if not save_path: return

        self.process_run_btn.setEnabled(False)
        self.process_stop_btn.setEnabled(True)
        self.worker = BulkProcessWorker(self.uploaded_files, template_to_use, save_path)
        self.worker.template_name = template_name
        
        self.worker.log.connect(self.process_log.append)
        self.worker.progress.connect(self.process_progress.setValue)
        self.worker.finished.connect(self.on_bulk_process_finished)
        self.worker.error.connect(self.on_bulk_process_error)
        self.worker.start()

    def update_manager_combo(self):

        self.manager_combo.blockSignals(True)
        self.manager_combo.clear()
        self.manager_combo.addItem("-- Buat Template Baru --")
        if self.built_in_templates:
            self.manager_combo.insertSeparator(1)
            for name in sorted(self.built_in_templates): self.manager_combo.addItem(f"⚙️ {name}")
        if self.templates:
            self.manager_combo.insertSeparator(self.manager_combo.count())
            self.manager_combo.addItems(sorted(self.templates.keys()))
        self.manager_combo.blockSignals(False)
        self.load_template_for_editing(self.manager_combo.currentText())

    def load_template_for_editing(self, current_text):
        template_name = current_text.replace("⚙️ ", "").strip()
        is_built_in = template_name in self.built_in_templates
        is_custom = template_name in self.templates

        self.custom_template_group.setVisible(not is_built_in)
        self.manager_template_name.setEnabled(not is_built_in)
        self.manager_save_btn.setEnabled(not is_built_in)
        self.manager_delete_btn.setEnabled(is_custom)

        self.manager_detected_fields_list.clear()
        self.manager_rules_list.clear()

        if is_built_in:
            self.manager_template_name.setText("")
            self.manager_template_name.setPlaceholderText("Template bawaan tidak bisa diubah")
        elif is_custom:
            self.manager_template_name.setText(template_name)
            template = self.templates[template_name]
            for rule in template.get("aturan", []): self.manager_rules_list.addItem(rule)
            self.manager_separator_input.setText(template.get("pemisah", " - "))
        else: # Buat baru
            self.manager_template_name.clear()
            self.manager_template_name.setPlaceholderText("Masukkan nama untuk template baru")
            self.manager_separator_input.setText(" - ")

    def save_template(self):
        template_name = self.manager_template_name.text().strip()
        is_valid, error_msg = validate_template_name(template_name)
        if not is_valid:
            ValidationUtils.show_message(self, "Nama Tidak Valid", error_msg, QMessageBox.Warning)
            return
        
        rules = [self.manager_rules_list.item(i).text() for i in range(self.manager_rules_list.count())]
        if not rules:
            ValidationUtils.show_message(self, "Template Kosong", "Template harus memiliki minimal satu aturan.", QMessageBox.Warning)
            return
            
        template = {"aturan": rules, "pemisah": self.manager_separator_input.text()}
        self.templates[template_name] = template
        try:
            save_templates(self.templates)
            ValidationUtils.show_message(self, "Sukses", f"Template '{template_name}' berhasil disimpan.")
            self.update_all_combos()
            self.manager_combo.setCurrentText(template_name)
        except (TemplateError, ConfigError) as e:
            ValidationUtils.show_message(self, "Error", f"Gagal menyimpan: {e}", QMessageBox.Critical)

    def delete_template(self):
        current_text = self.manager_combo.currentText()
        if not current_text or current_text.startswith("⚙️") or current_text not in self.templates:
            ValidationUtils.show_message(self, "Info", "Pilih template kustom untuk dihapus.", QMessageBox.Warning)
            return
        
        reply = QMessageBox.question(self, "Konfirmasi", f"Yakin ingin menghapus template '{current_text}'?")
        if reply == QMessageBox.Yes:
            del self.templates[current_text]
            save_templates(self.templates)
            ValidationUtils.show_message(self, "Sukses", f"Template '{current_text}' telah dihapus.")
            self.update_all_combos()

    def update_process_combo(self):
        self.process_combo.blockSignals(True)
        self.process_combo.clear()
        if self.built_in_templates:
            for name in sorted(self.built_in_templates): self.process_combo.addItem(f"⚙️ {name}")
        if self.templates:
            self.process_combo.insertSeparator(self.process_combo.count())
            self.process_combo.addItems(sorted(self.templates.keys()))
        if self.process_combo.count() == 0: self.process_combo.addItem("-- Tidak ada template --")
        self.process_combo.blockSignals(False)
        self.update_process_format_label(self.process_combo.currentText())

    def update_process_format_label(self, current_text):

        template_name = current_text.replace("⚙️ ", "").strip()
        if template_name in self.built_in_templates:
            self.process_format_label.setText(f"<b>Format:</b> Otomatis untuk '{template_name}'")
        elif template_name in self.templates:
            template = self.templates[template_name]
            format_str = template.get("pemisah", " - ").join(template.get("aturan", []))
            self.process_format_label.setText(f"<b>Format:</b> {format_str}.pdf")
        else:
            self.process_format_label.setText("Pilih template terlebih dahulu")

    def stop_bulk_process(self):

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.process_log.append("⏹️ Proses dihentikan...")

    def on_bulk_process_finished(self, save_path, success, total):

        self.process_run_btn.setEnabled(True)
        self.process_stop_btn.setEnabled(False)
        ValidationUtils.show_message(self, "Proses Selesai", f"Proses selesai! {success}/{total} file berhasil diproses.\nDisimpan di: {save_path}")

    def on_bulk_process_error(self, message):

        self.process_run_btn.setEnabled(True)
        self.process_stop_btn.setEnabled(False)
        ValidationUtils.show_message(self, "Error", f"Terjadi kesalahan: {message}", QMessageBox.Critical)

    def select_bulk_files(self):

        files, _ = QFileDialog.getOpenFileNames(self, "Pilih File PDF", "", "PDF Files (*.pdf)")
        if files:
            self.uploaded_files.extend(files)
            self.process_file_list.addItems([Path(f).name for f in files])

    def clear_selected_files(self):

        self.uploaded_files.clear()
        self.process_file_list.clear()

    def detect_fields_from_sample(self):

        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih PDF Contoh", "", "PDF Files (*.pdf)")
        if not file_path: return
        is_valid, msg = validate_pdf_file(file_path)
        if not is_valid:
            ValidationUtils.show_message(self, "File Tidak Valid", msg, QMessageBox.Warning)
            return
        try:
            fields = extract_pdf_fields(file_path)
            self.manager_detected_fields_list.clear()
            for key, value in fields.items():
                item = QListWidgetItem(f"{key}: {value[:50]}...")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.manager_detected_fields_list.addItem(item)
        except (FileValidationError, PDFProcessingError) as e:
            ValidationUtils.show_message(self, "Error Ekstraksi", str(e), QMessageBox.Warning)
            
    def update_rules_from_checkbox(self, item):

        field_name = item.text().split(":")[0].strip()
        if item.checkState() == Qt.Checked:
            if not self.manager_rules_list.findItems(field_name, Qt.MatchExactly):
                self.manager_rules_list.addItem(field_name)
        else:
            for found_item in self.manager_rules_list.findItems(field_name, Qt.MatchExactly):
                self.manager_rules_list.takeItem(self.manager_rules_list.row(found_item))

    def update_all_combos(self):

        self.update_manager_combo()
        self.update_process_combo()
        self.update_stats_label()
        
    def update_stats_label(self):

        total_templates = len(self.templates) + len(self.built_in_templates)
        self.stats_label.setText(f"Total Template Tersedia: {total_templates} ({len(self.built_in_templates)} bawaan, {len(self.templates)} kustom)")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDFRenamerApp()
    window.show()
    sys.exit(app.exec_())