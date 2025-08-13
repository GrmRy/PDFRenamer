import sys
from PyQt5.QtWidgets import QApplication
from ui_main import PDFRenamerApp

if __name__ == "__main__":
    """
    Titik masuk utama aplikasi.
    Menginisialisasi QApplication dan menampilkan jendela utama.
    """
    app = QApplication(sys.argv)
    window = PDFRenamerApp()
    window.show()
    sys.exit(app.exec_())