import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QLabel, QFileDialog, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
    QMessageBox, QComboBox, QTextEdit, QCheckBox, QSpinBox, QGroupBox, QScrollArea)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QPalette
from pathlib import Path
import logging

from pdf_tools import (extract_pdf_fields, process_single_pdf, validate_pdf_file, 
                      validate_template_name, FileValidationError, PDFProcessingError)
from utils import (load_templates, save_templates, TemplateError, ConfigError,
                  get_available_backups, restore_from_backup, validate_template_structure)
from zip_tools import save_zip, ZipError, ZipValidationError, verify_zip_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_renamer.log'),
        logging.StreamHandler()
    ]
)

# --- Enhanced Worker Thread untuk Proses Massal ---
class BulkProcessWorker(QThread):
    """Enhanced worker thread dengan validation dan error handling yang lebih baik."""
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, bool, str)  # filename, success, message
    finished = pyqtSignal(str, int, int)  # zip_path, success_count, total_count
    error = pyqtSignal(str)

    def __init__(self, uploaded_files, template, save_path):
        super().__init__()
        self.uploaded_files = uploaded_files
        self.template = template
        self.save_path = save_path
        self.is_running = True
        self.success_count = 0
        self.error_count = 0

    def run(self):
        try:
            total_files = len(self.uploaded_files)
            self.log.emit(f"🚀 Memulai proses untuk {total_files} file...")
            
            # Validate template first
            is_valid, error_msg = validate_template_structure(self.template)
            if not is_valid:
                self.error.emit(f"Template tidak valid: {error_msg}")
                return
            
            renamed_data = {}
            processing_errors = []
            
            for i, file_path in enumerate(self.uploaded_files):
                if not self.is_running:
                    self.log.emit("❌ Proses dibatalkan oleh pengguna.")
                    return
                
                try:
                    # Process single file with enhanced error handling
                    new_name, original_content, error_msg = process_single_pdf(file_path, self.template)
                    
                    if new_name and original_content:
                        # Check for filename conflicts
                        original_new_name = new_name
                        counter = 1
                        while new_name in renamed_data:
                            name_part, ext = original_new_name.rsplit('.', 1)
                            new_name = f"{name_part}_{counter}.{ext}"
                            counter += 1
                        
                        renamed_data[new_name] = original_content
                        self.success_count += 1
                        self.file_processed.emit(Path(file_path).name, True, f"✅ Berhasil → {new_name}")
                        self.log.emit(f"✅ [{i+1}/{total_files}] {Path(file_path).name} → {new_name}")
                    else:
                        self.error_count += 1
                        error_message = error_msg or "Gagal memproses file"
                        processing_errors.append(f"{Path(file_path).name}: {error_message}")
                        self.file_processed.emit(Path(file_path).name, False, f"❌ {error_message}")
                        self.log.emit(f"❌ [{i+1}/{total_files}] {Path(file_path).name}: {error_message}")
                
                except Exception as e:
                    self.error_count += 1
                    error_message = f"Error tak terduga: {str(e)}"
                    processing_errors.append(f"{Path(file_path).name}: {error_message}")
                    self.file_processed.emit(Path(file_path).name, False, error_message)
                    self.log.emit(f"💥 [{i+1}/{total_files}] {Path(file_path).name}: {error_message}")
                
                # Update progress
                progress_percent = int((i + 1) / total_files * 90)  # Reserve 10% for ZIP creation
                self.progress.emit(progress_percent)
            
            # Summary of processing
            self.log.emit(f"\n📊 Ringkasan Pemrosesan:")
            self.log.emit(f"✅ Berhasil: {self.success_count} file")
            self.log.emit(f"❌ Gagal: {self.error_count} file")
            
            if not renamed_data:
                self.error.emit("Tidak ada file yang berhasil diproses. Periksa log untuk detail error.")
                return
            
            # Create ZIP file
            self.log.emit(f"\n📦 Membuat file ZIP dengan {len(renamed_data)} file...")
            try:
                save_zip(renamed_data, self.save_path)
                
                # Verify ZIP file
                is_valid, verify_msg, file_count = verify_zip_file(self.save_path)
                if not is_valid:
                    self.error.emit(f"ZIP file gagal verifikasi: {verify_msg}")
                    return
                
                self.progress.emit(100)
                self.finished.emit(self.save_path, self.success_count, total_files)
                
            except (ZipError, ZipValidationError) as e:
                self.error.emit(f"Gagal membuat ZIP: {str(e)}")
            except Exception as e:
                self.error.emit(f"Error tak terduga saat membuat ZIP: {str(e)}")
            
        except Exception as e:
            self.error.emit(f"Error kritis dalam worker thread: {str(e)}")

    def stop(self):
        self.is_running = False

# --- Enhanced Input Validation Utilities ---
class ValidationUtils:
    @staticmethod
    def show_validation_error(parent, title, message):
        """Show a standardized validation error message."""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    @staticmethod
    def show_critical_error(parent, title, message):
        """Show a critical error message."""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    @staticmethod
    def show_success_message(parent, title, message):
        """Show a success message."""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

# --- Enhanced Main Application Window ---
class PDFRenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Renamer Pro (Desktop Edition) - Enhanced")
        self.setGeometry(100, 100, 1000, 700)
        
        # Initialize data
        try:
            self.templates = load_templates()
        except ConfigError as e:
            ValidationUtils.show_critical_error(self, "Error Konfigurasi", 
                                               f"Gagal memuat konfigurasi: {str(e)}")
            self.templates = {}
        
        self.worker = None
        self.uploaded_files = []
        
        # Setup logging for UI
        self.setup_logging()
        
        # Initialize UI
        self.init_ui()
        
        # Setup auto-save timer for templates
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save_templates)
        self.auto_save_timer.start(300000)  # Auto-save every 5 minutes

    def setup_logging(self):
        """Setup logging configuration."""
        try:
            logging.info("PDF Renamer Pro started")
        except Exception:
            pass  # Ignore logging setup errors

    def init_ui(self):
        # Main layout with enhanced styling
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Enhanced sidebar navigation
        nav_widget = QWidget()
        nav_widget.setMinimumWidth(200)
        nav_widget.setMaximumWidth(250)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setSpacing(5)

        # Navigation buttons with icons
        self.btn_dashboard = QPushButton("🏠 Dashboard")
        self.btn_manager = QPushButton("🛠️ Manajer Template")
        self.btn_process = QPushButton("⚙️ Proses Massal")
        self.btn_settings = QPushButton("⚙️ Pengaturan")

        # Style navigation buttons
        nav_buttons = [self.btn_dashboard, self.btn_manager, self.btn_process, self.btn_settings]
        for btn in nav_buttons:
            btn.setMinimumHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 8px 12px;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    background-color: #f5f5f5;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """)

        nav_layout.addWidget(self.btn_dashboard)
        nav_layout.addWidget(self.btn_manager)
        nav_layout.addWidget(self.btn_process)
        nav_layout.addWidget(self.btn_settings)
        nav_layout.addStretch()

        # Pages (Stacked Widget)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.create_dashboard_page())     # Index 0
        self.pages.addWidget(self.create_manager_page())       # Index 1
        self.pages.addWidget(self.create_process_page())       # Index 2
        self.pages.addWidget(self.create_settings_page())      # Index 3

        main_layout.addWidget(nav_widget)
        main_layout.addWidget(self.pages, 1)

        # Connect navigation signals
        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0))
        self.btn_manager.clicked.connect(lambda: self.switch_page(1))
        self.btn_process.clicked.connect(lambda: self.switch_page(2))
        self.btn_settings.clicked.connect(lambda: self.switch_page(3))

        # Update UI components
        self.update_all_combos()

    def switch_page(self, page_index):
        """Switch to specified page with validation."""
        try:
            if 0 <= page_index < self.pages.count():
                self.pages.setCurrentIndex(page_index)
            else:
                logging.warning(f"Invalid page index: {page_index}")
        except Exception as e:
            logging.error(f"Error switching page: {e}")

    # --- Enhanced Dashboard Page ---
    def create_dashboard_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)

        # Title with styling
        title = QLabel("Selamat Datang di PDF Renamer Pro!")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel("""
        Aplikasi ini dirancang untuk menyederhanakan tugas me-rename file PDF secara massal.
        Dengan membuat 'template', Anda bisa me-rename ratusan file sesuai format yang diinginkan 
        hanya dengan beberapa klik.
        """)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #34495e; font-size: 14px; line-height: 1.4;")
        layout.addWidget(desc)

        # Statistics group
        stats_group = QGroupBox("Statistik Anda")
        stats_group.setFont(QFont("Arial", 14, QFont.Bold))
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_label = QLabel(f"Jumlah Template Tersimpan: {len(self.templates)} Template")
        self.stats_label.setStyleSheet("font-size: 13px; color: #2c3e50;")
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(stats_group)

        # Quick start guide
        guide_group = QGroupBox("Panduan Cepat")
        guide_group.setFont(QFont("Arial", 14, QFont.Bold))
        guide_layout = QVBoxLayout(guide_group)
        
        steps = [
            "1. Buka 🛠️ Manajer Template untuk membuat template rename pertama",
            "2. Upload contoh PDF untuk mendeteksi field yang tersedia",
            "3. Pilih field yang ingin digunakan dan atur urutannya",
            "4. Simpan template dengan nama yang mudah diingat",
            "5. Buka ⚙️ Proses Massal untuk menggunakan template tersebut",
            "6. Pilih semua file PDF yang ingin di-rename",
            "7. Jalankan proses dan download hasil dalam file ZIP"
        ]
        
        for step in steps:
            step_label = QLabel(step)
            step_label.setStyleSheet("margin: 3px 0px; color: #34495e;")
            guide_layout.addWidget(step_label)
        
        layout.addWidget(guide_group)
        
        layout.addStretch()
        return widget

    # --- Enhanced Template Manager Page ---
    def create_manager_page(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Template selection section
        selection_group = QGroupBox("Pilih/Edit Template")
        selection_layout = QVBoxLayout(selection_group)
        
        # Template combo and name input
        combo_layout = QHBoxLayout()
        combo_layout.addWidget(QLabel("Template:"))
        self.manager_combo = QComboBox()
        self.manager_combo.setMinimumWidth(200)
        combo_layout.addWidget(self.manager_combo)
        combo_layout.addStretch()
        selection_layout.addLayout(combo_layout)
        
        # Template name input with validation
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nama Template:"))
        self.manager_template_name = QLineEdit()
        self.manager_template_name.setPlaceholderText("Masukkan nama template (2-50 karakter)")
        self.manager_template_name.textChanged.connect(self.validate_template_name_input)
        name_layout.addWidget(self.manager_template_name)
        
        self.name_validation_label = QLabel("")
        self.name_validation_label.setStyleSheet("color: red; font-size: 11px;")
        selection_layout.addLayout(name_layout)
        selection_layout.addWidget(self.name_validation_label)
        
        layout.addWidget(selection_group)

        # PDF upload and field detection
        detection_group = QGroupBox("Deteksi Field dari PDF")
        detection_layout = QVBoxLayout(detection_group)
        
        upload_layout = QHBoxLayout()
        self.manager_upload_btn = QPushButton("📄 Unggah PDF Contoh")
        self.manager_upload_btn.setMinimumHeight(35)
        upload_layout.addWidget(self.manager_upload_btn)
        upload_layout.addStretch()
        detection_layout.addLayout(upload_layout)
        
        detection_layout.addWidget(QLabel("Field yang Ditemukan (centang untuk digunakan):"))
        self.manager_detected_fields_list = QListWidget()
        self.manager_detected_fields_list.setMaximumHeight(200)
        detection_layout.addWidget(self.manager_detected_fields_list)
        
        layout.addWidget(detection_group)

        # Rules ordering
        rules_group = QGroupBox("Aturan Template")
        rules_layout = QVBoxLayout(rules_group)
        
        rules_layout.addWidget(QLabel("Urutan Field dalam Nama File (drag & drop untuk mengubah urutan):"))
        self.manager_rules_list = QListWidget()
        self.manager_rules_list.setDragDropMode(QListWidget.InternalMove)
        self.manager_rules_list.setMaximumHeight(150)
        rules_layout.addWidget(self.manager_rules_list)
        
        # Separator input
        separator_layout = QHBoxLayout()
        separator_layout.addWidget(QLabel("Pemisah:"))
        self.manager_separator_input = QLineEdit(" - ")
        self.manager_separator_input.setMaximumWidth(100)
        separator_layout.addWidget(self.manager_separator_input)
        separator_layout.addStretch()
        rules_layout.addLayout(separator_layout)
        
        layout.addWidget(rules_group)

        # Action buttons
        button_layout = QHBoxLayout()
        self.manager_save_btn = QPushButton("💾 Simpan Template")
        self.manager_save_btn.setMinimumHeight(35)
        self.manager_save_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        
        self.manager_delete_btn = QPushButton("🗑️ Hapus Template")
        self.manager_delete_btn.setMinimumHeight(35)
        self.manager_delete_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        
        button_layout.addWidget(self.manager_save_btn)
        button_layout.addWidget(self.manager_delete_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect signals
        self.manager_upload_btn.clicked.connect(self.detect_fields_from_sample)
        self.manager_combo.currentTextChanged.connect(self.load_template_for_editing)
        self.manager_detected_fields_list.itemChanged.connect(self.update_rules_from_checkbox)
        self.manager_save_btn.clicked.connect(self.save_template)
        self.manager_delete_btn.clicked.connect(self.delete_template)

        return scroll

    def validate_template_name_input(self):
        """Real-time validation of template name input."""
        name = self.manager_template_name.text()
        is_valid, error_msg = validate_template_name(name)
        
        if name and not is_valid:
            self.name_validation_label.setText(f"❌ {error_msg}")
            self.name_validation_label.setStyleSheet("color: red; font-size: 11px;")
            self.manager_save_btn.setEnabled(False)
        else:
            if name:
                self.name_validation_label.setText("✅ Nama template valid")
                self.name_validation_label.setStyleSheet("color: green; font-size: 11px;")
            else:
                self.name_validation_label.setText("")
            self.manager_save_btn.setEnabled(bool(name and is_valid))

    # --- Enhanced Process Page ---
    def create_process_page(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Step 1: Template Selection
        step1_group = QGroupBox("Langkah 1: Pilih Template")
        step1_layout = QVBoxLayout(step1_group)
        
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("Template:"))
        self.process_combo = QComboBox()
        self.process_combo.setMinimumWidth(200)
        template_layout.addWidget(self.process_combo)
        template_layout.addStretch()
        step1_layout.addLayout(template_layout)
        
        self.process_format_label = QLabel("Format Nama File: Pilih template terlebih dahulu")
        self.process_format_label.setStyleSheet("color: #34495e; font-style: italic; margin: 5px 0px;")
        step1_layout.addWidget(self.process_format_label)
        
        layout.addWidget(step1_group)

        # Step 2: File Selection
        step2_group = QGroupBox("Langkah 2: Pilih File PDF")
        step2_layout = QVBoxLayout(step2_group)
        
        upload_layout = QHBoxLayout()
        self.process_upload_btn = QPushButton("📁 Pilih File PDF...")
        self.process_upload_btn.setMinimumHeight(35)
        upload_layout.addWidget(self.process_upload_btn)
        
        self.process_clear_btn = QPushButton("🗑️ Hapus Semua")
        self.process_clear_btn.setMinimumHeight(35)
        upload_layout.addWidget(self.process_clear_btn)
        upload_layout.addStretch()
        step2_layout.addLayout(upload_layout)
        
        # File list with validation info
        file_info_layout = QHBoxLayout()
        self.process_file_count_label = QLabel("File dipilih: 0")
        self.process_file_validation_label = QLabel("")
        file_info_layout.addWidget(self.process_file_count_label)
        file_info_layout.addWidget(self.process_file_validation_label)
        file_info_layout.addStretch()
        step2_layout.addLayout(file_info_layout)
        
        self.process_file_list = QListWidget()
        self.process_file_list.setMaximumHeight(150)
        step2_layout.addWidget(self.process_file_list)
        
        layout.addWidget(step2_group)

        # Step 3: Processing
        step3_group = QGroupBox("Langkah 3: Proses dan Hasil")
        step3_layout = QVBoxLayout(step3_group)
        
        # Processing controls
        process_control_layout = QHBoxLayout()
        self.process_run_btn = QPushButton("🚀 MULAI PROSES")
        self.process_run_btn.setMinimumHeight(40)
        self.process_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        
        self.process_stop_btn = QPushButton("⏹️ STOP")
        self.process_stop_btn.setMinimumHeight(40)
        self.process_stop_btn.setEnabled(False)
        self.process_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        
        process_control_layout.addWidget(self.process_run_btn)
        process_control_layout.addWidget(self.process_stop_btn)
        process_control_layout.addStretch()
        step3_layout.addLayout(process_control_layout)
        
        # Progress bar
        self.process_progress = QProgressBar()
        self.process_progress.setMinimumHeight(25)
        step3_layout.addWidget(self.process_progress)
        
        # Processing status
        self.process_status_label = QLabel("Siap untuk memproses")
        self.process_status_label.setStyleSheet("color: #2c3e50; font-weight: bold;")
        step3_layout.addWidget(self.process_status_label)
        
        # Log area
        step3_layout.addWidget(QLabel("Log Proses:"))
        self.process_log = QTextEdit()
        self.process_log.setReadOnly(True)
        self.process_log.setMaximumHeight(200)
        self.process_log.setStyleSheet("font-family: monospace; font-size: 11px;")
        step3_layout.addWidget(self.process_log)
        
        layout.addWidget(step3_group)

        # Connect signals
        self.process_combo.currentTextChanged.connect(self.update_process_format_label)
        self.process_upload_btn.clicked.connect(self.select_bulk_files)
        self.process_clear_btn.clicked.connect(self.clear_selected_files)
        self.process_run_btn.clicked.connect(self.run_bulk_process)
        self.process_stop_btn.clicked.connect(self.stop_bulk_process)

        return scroll

    # --- Settings Page ---
    def create_settings_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)

        # Backup and Restore
        backup_group = QGroupBox("Backup & Restore Template")
        backup_layout = QVBoxLayout(backup_group)
        
        backup_info = QLabel("Backup otomatis dibuat setiap kali template disimpan.")
        backup_info.setStyleSheet("color: #7f8c8d; font-style: italic;")
        backup_layout.addWidget(backup_info)
        
        backup_btn_layout = QHBoxLayout()
        self.backup_list_btn = QPushButton("📋 Lihat Backup")
        self.restore_btn = QPushButton("♻️ Restore dari Backup")
        backup_btn_layout.addWidget(self.backup_list_btn)
        backup_btn_layout.addWidget(self.restore_btn)
        backup_btn_layout.addStretch()
        backup_layout.addLayout(backup_btn_layout)
        
        layout.addWidget(backup_group)

        # Application Settings
        app_group = QGroupBox("Pengaturan Aplikasi")
        app_layout = QVBoxLayout(app_group)
        
        # Auto-save setting
        autosave_layout = QHBoxLayout()
        self.autosave_checkbox = QCheckBox("Auto-save template setiap 5 menit")
        self.autosave_checkbox.setChecked(True)
        autosave_layout.addWidget(self.autosave_checkbox)
        autosave_layout.addStretch()
        app_layout.addLayout(autosave_layout)
        
        # Log level setting
        log_layout = QHBoxLayout()
        log_layout.addWidget(QLabel("Level Log:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText("INFO")
        log_layout.addWidget(self.log_level_combo)
        log_layout.addStretch()
        app_layout.addLayout(log_layout)
        
        layout.addWidget(app_group)

        # About section
        about_group = QGroupBox("Tentang Aplikasi")
        about_layout = QVBoxLayout(about_group)
        
        about_text = QLabel("""
        <b>PDF Renamer Pro - Enhanced Edition</b><br>
        Versi: 2.0.0<br>
        Aplikasi untuk rename massal file PDF berdasarkan konten.<br><br>
        <b>Fitur Baru:</b><br>
        • Validasi input yang komprehensif<br>
        • Error handling yang lebih baik<br>
        • Backup otomatis template<br>
        • Progress tracking yang detail<br>
        • UI yang lebih responsif
        """)
        about_text.setWordWrap(True)
        about_layout.addWidget(about_text)
        
        layout.addWidget(about_group)
        layout.addStretch()

        # Connect signals
        self.backup_list_btn.clicked.connect(self.show_backup_list)
        self.restore_btn.clicked.connect(self.restore_from_backup_dialog)
        self.autosave_checkbox.toggled.connect(self.toggle_autosave)
        self.log_level_combo.currentTextChanged.connect(self.change_log_level)

        return widget

    # --- Enhanced Template Manager Functions ---
    def update_manager_combo(self):
        """Update manager combo with validation."""
        try:
            self.manager_combo.blockSignals(True)
            self.manager_combo.clear()
            self.manager_combo.addItem("-- Buat Baru --")
            
            if self.templates:
                sorted_templates = sorted(self.templates.keys())
                self.manager_combo.addItems(sorted_templates)
            
            self.manager_combo.blockSignals(False)
        except Exception as e:
            logging.error(f"Error updating manager combo: {e}")

    def load_template_for_editing(self, template_name):
        """Load template for editing with validation."""
        try:
            self.manager_detected_fields_list.clear()
            self.manager_rules_list.clear()
            
            if template_name and template_name != "-- Buat Baru --":
                if template_name in self.templates:
                    self.manager_template_name.setText(template_name)
                    template = self.templates[template_name]
                    
                    # Validate template structure
                    is_valid, error_msg = validate_template_structure(template)
                    if not is_valid:
                        ValidationUtils.show_validation_error(
                            self, "Template Tidak Valid", 
                            f"Template '{template_name}' memiliki struktur yang tidak valid: {error_msg}"
                        )
                        return
                    
                    rules = template.get("aturan", [])
                    separator = template.get("pemisah", " - ")
                    
                    for rule in rules:
                        self.manager_rules_list.addItem(rule)
                    
                    self.manager_separator_input.setText(separator)
                else:
                    ValidationUtils.show_validation_error(
                        self, "Template Tidak Ditemukan",
                        f"Template '{template_name}' tidak ditemukan."
                    )
            else:
                self.manager_template_name.clear()
                self.manager_separator_input.setText(" - ")
                
        except Exception as e:
            logging.error(f"Error loading template for editing: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Gagal memuat template: {str(e)}"
            )

    def detect_fields_from_sample(self):
        """Detect fields from sample PDF with enhanced validation."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Pilih PDF Contoh", "", "PDF Files (*.pdf)"
            )
            if not file_path:
                return

            # Validate file first
            is_valid, error_msg = validate_pdf_file(file_path)
            if not is_valid:
                ValidationUtils.show_validation_error(
                    self, "File Tidak Valid", error_msg
                )
                return

            # Clear previous results
            self.manager_detected_fields_list.clear()
            self.manager_rules_list.clear()

            # Extract fields
            try:
                fields = extract_pdf_fields(file_path)
                
                if not fields:
                    ValidationUtils.show_validation_error(
                        self, "Tidak Ada Field", 
                        "Tidak ada field yang dapat dideteksi dari file ini.\n"
                        "Pastikan PDF mengandung teks dengan format 'Label: Nilai'."
                    )
                    return
                
                # Add fields to list with checkboxes
                for key, value in fields.items():
                    # Truncate long values for display
                    display_value = value[:50] + "..." if len(value) > 50 else value
                    item = QListWidgetItem(f"{key}: {display_value}")
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    item.setToolTip(f"Field: {key}\nNilai Lengkap: {value}")
                    self.manager_detected_fields_list.addItem(item)
                
                self.process_log.append(f"✅ Berhasil mendeteksi {len(fields)} field dari {Path(file_path).name}")
                
            except (FileValidationError, PDFProcessingError) as e:
                ValidationUtils.show_validation_error(
                    self, "Error Pemrosesan PDF", str(e)
                )
            except Exception as e:
                ValidationUtils.show_critical_error(
                    self, "Error Tak Terduga", f"Error saat memproses PDF: {str(e)}"
                )
                
        except Exception as e:
            logging.error(f"Error in detect_fields_from_sample: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Error tak terduga: {str(e)}"
            )

    def update_rules_from_checkbox(self, item):
        """Update rules list when checkbox state changes."""
        try:
            field_name = item.text().split(":")[0].strip()
            
            if item.checkState() == Qt.Checked:
                # Add to rules if not already present
                existing_items = [self.manager_rules_list.item(i).text() 
                                for i in range(self.manager_rules_list.count())]
                if field_name not in existing_items:
                    self.manager_rules_list.addItem(field_name)
            else:
                # Remove from rules
                items_to_remove = self.manager_rules_list.findItems(field_name, Qt.MatchExactly)
                for item_to_remove in items_to_remove:
                    self.manager_rules_list.takeItem(self.manager_rules_list.row(item_to_remove))
                    
        except Exception as e:
            logging.error(f"Error updating rules from checkbox: {e}")

    def save_template(self):
        """Save template with comprehensive validation."""
        try:
            template_name = self.manager_template_name.text().strip()
            
            # Validate template name
            is_valid, error_msg = validate_template_name(template_name)
            if not is_valid:
                ValidationUtils.show_validation_error(
                    self, "Nama Template Tidak Valid", error_msg
                )
                return

            # Get rules
            rules = [self.manager_rules_list.item(i).text() 
                    for i in range(self.manager_rules_list.count())]
            
            if not rules:
                ValidationUtils.show_validation_error(
                    self, "Template Tidak Lengkap", 
                    "Template harus memiliki minimal satu field/aturan."
                )
                return

            # Get separator
            separator = self.manager_separator_input.text()
            if not separator.strip():
                separator = " - "  # Default

            # Create template object
            template = {
                "aturan": rules,
                "pemisah": separator
            }

            # Validate template structure
            is_valid, error_msg = validate_template_structure(template)
            if not is_valid:
                ValidationUtils.show_validation_error(
                    self, "Template Tidak Valid", error_msg
                )
                return

            # Check for overwrite
            if template_name in self.templates:
                reply = QMessageBox.question(
                    self, "Template Sudah Ada",
                    f"Template '{template_name}' sudah ada. Ingin menimpa?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            # Save template
            self.templates[template_name] = template
            
            try:
                save_templates(self.templates)
                ValidationUtils.show_success_message(
                    self, "Sukses", f"Template '{template_name}' berhasil disimpan."
                )
                
                # Update UI
                self.update_all_combos()
                self.manager_combo.setCurrentText(template_name)
                self.update_stats_label()
                
                logging.info(f"Template saved: {template_name}")
                
            except (TemplateError, ConfigError) as e:
                ValidationUtils.show_critical_error(
                    self, "Error Menyimpan", f"Gagal menyimpan template: {str(e)}"
                )
            
        except Exception as e:
            logging.error(f"Error saving template: {e}")
            ValidationUtils.show_critical_error(
                self, "Error Tak Terduga", f"Error saat menyimpan template: {str(e)}"
            )

    def delete_template(self):
        """Delete template with confirmation."""
        try:
            template_name = self.manager_combo.currentText()
            
            if not template_name or template_name == "-- Buat Baru --":
                ValidationUtils.show_validation_error(
                    self, "Pilihan Tidak Valid", 
                    "Pilih template yang valid untuk dihapus."
                )
                return

            if template_name not in self.templates:
                ValidationUtils.show_validation_error(
                    self, "Template Tidak Ditemukan",
                    f"Template '{template_name}' tidak ditemukan."
                )
                return

            # Confirmation dialog
            reply = QMessageBox.question(
                self, "Konfirmasi Hapus",
                f"Anda yakin ingin menghapus template '{template_name}'?\n"
                "Tindakan ini tidak dapat dibatalkan.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                del self.templates[template_name]
                
                try:
                    save_templates(self.templates)
                    ValidationUtils.show_success_message(
                        self, "Sukses", f"Template '{template_name}' telah dihapus."
                    )
                    
                    # Clear UI
                    self.manager_template_name.clear()
                    self.manager_rules_list.clear()
                    self.manager_detected_fields_list.clear()
                    self.manager_separator_input.setText(" - ")
                    
                    # Update UI
                    self.update_all_combos()
                    self.update_stats_label()
                    
                    logging.info(f"Template deleted: {template_name}")
                    
                except (TemplateError, ConfigError) as e:
                    ValidationUtils.show_critical_error(
                        self, "Error Menghapus", f"Gagal menghapus template: {str(e)}"
                    )
                
        except Exception as e:
            logging.error(f"Error deleting template: {e}")
            ValidationUtils.show_critical_error(
                self, "Error Tak Terduga", f"Error saat menghapus template: {str(e)}"
            )

    # --- Enhanced Process Functions ---
    def update_process_combo(self):
        """Update process combo with templates."""
        try:
            self.process_combo.blockSignals(True)
            self.process_combo.clear()
            
            if self.templates:
                sorted_templates = sorted(self.templates.keys())
                self.process_combo.addItems(sorted_templates)
            else:
                self.process_combo.addItem("-- Tidak ada template --")
            
            self.process_combo.blockSignals(False)
            self.update_process_format_label(self.process_combo.currentText())
            
        except Exception as e:
            logging.error(f"Error updating process combo: {e}")

    def update_process_format_label(self, template_name):
        """Update format label based on selected template."""
        try:
            if template_name and template_name in self.templates:
                template = self.templates[template_name]
                separator = template.get("pemisah", " - ")
                rules = template.get("aturan", [])
                
                if rules:
                    format_str = separator.join(rules)
                    self.process_format_label.setText(f"<b>Format:</b> {format_str}.pdf")
                    self.process_format_label.setStyleSheet("color: #27ae60; font-weight: bold;")
                else:
                    self.process_format_label.setText("Template tidak memiliki aturan")
                    self.process_format_label.setStyleSheet("color: #e74c3c;")
            else:
                self.process_format_label.setText("Pilih template terlebih dahulu")
                self.process_format_label.setStyleSheet("color: #95a5a6; font-style: italic;")
                
        except Exception as e:
            logging.error(f"Error updating format label: {e}")
            self.process_format_label.setText("Error memuat template")
            self.process_format_label.setStyleSheet("color: #e74c3c;")

    def select_bulk_files(self):
        """Select multiple PDF files with validation."""
        try:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Pilih File PDF untuk Diproses", "", "PDF Files (*.pdf)"
            )
            
            if not files:
                return

            # Validate each file
            valid_files = []
            invalid_files = []
            
            for file_path in files:
                is_valid, error_msg = validate_pdf_file(file_path)
                if is_valid:
                    valid_files.append(file_path)
                else:
                    invalid_files.append((Path(file_path).name, error_msg))

            # Update file list
            self.uploaded_files = valid_files
            self.process_file_list.clear()
            
            for file_path in valid_files:
                self.process_file_list.addItem(Path(file_path).name)

            # Update UI labels
            self.update_file_count_labels(len(valid_files), len(invalid_files))

            # Show validation results
            if invalid_files:
                invalid_msg = "\n".join([f"• {name}: {error}" for name, error in invalid_files[:5]])
                if len(invalid_files) > 5:
                    invalid_msg += f"\n... dan {len(invalid_files) - 5} file lainnya"
                
                ValidationUtils.show_validation_error(
                    self, "Beberapa File Tidak Valid",
                    f"{len(invalid_files)} file dilewati karena tidak valid:\n\n{invalid_msg}"
                )

            if valid_files:
                self.process_log.append(f"✅ {len(valid_files)} file PDF berhasil dipilih")
                if invalid_files:
                    self.process_log.append(f"⚠️ {len(invalid_files)} file dilewati karena tidak valid")

        except Exception as e:
            logging.error(f"Error selecting bulk files: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Error saat memilih file: {str(e)}"
            )

    def clear_selected_files(self):
        """Clear selected files."""
        self.uploaded_files = []
        self.process_file_list.clear()
        self.update_file_count_labels(0, 0)
        self.process_log.append("🗑️ Daftar file dikosongkan")

    def update_file_count_labels(self, valid_count, invalid_count):
        """Update file count labels."""
        self.process_file_count_label.setText(f"File dipilih: {valid_count}")
        
        if invalid_count > 0:
            self.process_file_validation_label.setText(f"❌ {invalid_count} file tidak valid")
            self.process_file_validation_label.setStyleSheet("color: #e74c3c;")
        else:
            self.process_file_validation_label.setText("✅ Semua file valid")
            self.process_file_validation_label.setStyleSheet("color: #27ae60;")

    def run_bulk_process(self):
        """Run bulk processing with validation."""
        try:
            # Validate template selection
            template_name = self.process_combo.currentText()
            if not template_name or template_name == "-- Tidak ada template --":
                ValidationUtils.show_validation_error(
                    self, "Template Belum Dipilih", 
                    "Pilih template terlebih dahulu sebelum memproses."
                )
                return

            if template_name not in self.templates:
                ValidationUtils.show_validation_error(
                    self, "Template Tidak Valid",
                    f"Template '{template_name}' tidak ditemukan."
                )
                return

            # Validate file selection
            if not hasattr(self, 'uploaded_files') or not self.uploaded_files:
                ValidationUtils.show_validation_error(
                    self, "File Belum Dipilih",
                    "Pilih file PDF yang akan diproses terlebih dahulu."
                )
                return

            # Get save location
            default_name = f"Hasil Rename ({template_name}).zip"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Simpan Hasil ke File ZIP", default_name, "Zip Files (*.zip)"
            )
            
            if not save_path:
                return

            # Validate save path
            from zip_tools import validate_zip_path
            is_valid, error_msg = validate_zip_path(save_path)
            if not is_valid:
                ValidationUtils.show_validation_error(
                    self, "Path Tidak Valid", error_msg
                )
                return

            # Start processing
            self.process_run_btn.setEnabled(False)
            self.process_stop_btn.setEnabled(True)
            self.process_log.clear()
            self.process_progress.setValue(0)
            self.process_status_label.setText("Memproses...")
            
            template = self.templates[template_name]
            self.worker = BulkProcessWorker(self.uploaded_files, template, save_path)
            
            # Connect worker signals
            self.worker.log.connect(self.process_log.append)
            self.worker.progress.connect(self.process_progress.setValue)
            self.worker.file_processed.connect(self.on_file_processed)
            self.worker.finished.connect(self.on_bulk_process_finished)
            self.worker.error.connect(self.on_bulk_process_error)
            
            self.worker.start()
            
            logging.info(f"Started bulk processing: {len(self.uploaded_files)} files with template '{template_name}'")

        except Exception as e:
            logging.error(f"Error starting bulk process: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Error saat memulai proses: {str(e)}"
            )

    def stop_bulk_process(self):
        """Stop the bulk processing."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.process_status_label.setText("Menghentikan...")
            self.process_log.append("⏹️ Proses dihentikan oleh pengguna")

    def on_file_processed(self, filename, success, message):
        """Handle individual file processing result."""
        # This can be used for more detailed progress tracking if needed
        pass

    def on_bulk_process_finished(self, save_path, success_count, total_count):
        """Handle successful completion of bulk processing."""
        try:
            self.process_run_btn.setEnabled(True)
            self.process_stop_btn.setEnabled(False)
            self.process_status_label.setText("Selesai")
            
            # Show completion message
            completion_msg = (
                f"Proses selesai!\n\n"
                f"File berhasil diproses: {success_count}/{total_count}\n"
                f"File ZIP disimpan di: {save_path}"
            )
            
            ValidationUtils.show_success_message(self, "Proses Selesai", completion_msg)
            
            self.worker = None
            logging.info(f"Bulk processing completed: {success_count}/{total_count} files processed")

        except Exception as e:
            logging.error(f"Error in bulk process finished handler: {e}")

    def on_bulk_process_error(self, message):
        """Handle bulk processing error."""
        try:
            self.process_run_btn.setEnabled(True)
            self.process_stop_btn.setEnabled(False)
            self.process_status_label.setText("Error")
            
            ValidationUtils.show_critical_error(
                self, "Error Pemrosesan", f"Terjadi kesalahan selama proses:\n\n{message}"
            )
            
            self.worker = None
            logging.error(f"Bulk processing error: {message}")

        except Exception as e:
            logging.error(f"Error in bulk process error handler: {e}")

    # --- Settings Functions ---
    def show_backup_list(self):
        """Show list of available backups."""
        try:
            backups = get_available_backups()
            
            if not backups:
                ValidationUtils.show_success_message(
                    self, "Tidak Ada Backup", "Belum ada file backup yang tersedia."
                )
                return

            # Create backup list dialog
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Daftar Backup Template")
            dialog.setMinimumSize(400, 300)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("File backup yang tersedia:"))
            
            backup_list = QListWidget()
            for backup in backups:
                backup_list.addItem(f"{backup.name} ({backup.stat().st_mtime})")
            
            layout.addWidget(backup_list)
            
            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            
            dialog.exec_()

        except Exception as e:
            logging.error(f"Error showing backup list: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Error menampilkan daftar backup: {str(e)}"
            )

    def restore_from_backup_dialog(self):
        """Show restore from backup dialog."""
        try:
            backups = get_available_backups()
            
            if not backups:
                ValidationUtils.show_success_message(
                    self, "Tidak Ada Backup", "Belum ada file backup untuk di-restore."
                )
                return

            # Create selection dialog
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Restore Template dari Backup")
            dialog.setMinimumSize(500, 400)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("Pilih backup untuk di-restore:\n(Template saat ini akan diganti)"))
            
            backup_list = QListWidget()
            for backup in backups:
                import datetime
                mod_time = datetime.datetime.fromtimestamp(backup.stat().st_mtime)
                backup_list.addItem(f"{backup.name} - {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            layout.addWidget(backup_list)
            
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec_() == QDialog.Accepted:
                selected_items = backup_list.selectedItems()
                if selected_items:
                    selected_index = backup_list.row(selected_items[0])
                    selected_backup = backups[selected_index]
                    
                    # Confirm restore
                    reply = QMessageBox.question(
                        self, "Konfirmasi Restore",
                        f"Restore template dari backup:\n{selected_backup.name}\n\n"
                        "Template saat ini akan diganti. Lanjutkan?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        try:
                            restored_templates = restore_from_backup(str(selected_backup))
                            self.templates = restored_templates
                            self.update_all_combos()
                            self.update_stats_label()
                            
                            ValidationUtils.show_success_message(
                                self, "Restore Berhasil", 
                                f"Template berhasil di-restore dari backup.\n"
                                f"Total template: {len(restored_templates)}"
                            )
                            
                        except ConfigError as e:
                            ValidationUtils.show_critical_error(
                                self, "Error Restore", f"Gagal restore dari backup: {str(e)}"
                            )

        except Exception as e:
            logging.error(f"Error in restore dialog: {e}")
            ValidationUtils.show_critical_error(
                self, "Error", f"Error saat restore: {str(e)}"
            )

    def toggle_autosave(self, enabled):
        """Toggle auto-save functionality."""
        try:
            if enabled:
                self.auto_save_timer.start(300000)  # 5 minutes
                logging.info("Auto-save enabled")
            else:
                self.auto_save_timer.stop()
                logging.info("Auto-save disabled")
        except Exception as e:
            logging.error(f"Error toggling auto-save: {e}")

    def change_log_level(self, level):
        """Change logging level."""
        try:
            level_map = {
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR
            }
            
            if level in level_map:
                logging.getLogger().setLevel(level_map[level])
                logging.info(f"Log level changed to: {level}")
        except Exception as e:
            logging.error(f"Error changing log level: {e}")

    def auto_save_templates(self):
        """Auto-save templates periodically."""
        try:
            if self.templates:
                save_templates(self.templates)
                logging.info("Templates auto-saved")
        except Exception as e:
            logging.warning(f"Auto-save failed: {e}")

    # --- Utility Functions ---
    def update_all_combos(self):
        """Update all combo boxes."""
        try:
            self.update_manager_combo()
            self.update_process_combo()
        except Exception as e:
            logging.error(f"Error updating combos: {e}")

    def update_stats_label(self):
        """Update statistics label on dashboard."""
        try:
            self.stats_label.setText(f"Jumlah Template Tersimpan: {len(self.templates)} Template")
        except Exception as e:
            logging.error(f"Error updating stats label: {e}")

    def closeEvent(self, event):
        """Handle application close event."""
        try:
            # Stop worker thread if running
            if self.worker and self.worker.isRunning():
                self.worker.stop()
                self.worker.wait(5000)  # Wait max 5 seconds
            
            # Stop auto-save timer
            if hasattr(self, 'auto_save_timer'):
                self.auto_save_timer.stop()
            
            # Final save of templates
            try:
                if self.templates:
                    save_templates(self.templates)
                    logging.info("Final save completed")
            except Exception as e:
                logging.warning(f"Final save failed: {e}")
            
            logging.info("PDF Renamer Pro closed")
            event.accept()
            
        except Exception as e:
            logging.error(f"Error during close: {e}")
            event.accept()  # Still close the application