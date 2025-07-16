import sys
import os
import shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QLabel, QFileDialog, QLineEdit, QProgressBar, QMessageBox,
    QHBoxLayout, QTextEdit, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QDateTime
from PyQt6.QtGui import QIntValidator

# --- (Bagian PdfSplitterThread tanpa logika pembatalan) ---
class PdfSplitterThread(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, dict)

    def __init__(self, source_folder, destination_folder, size_limit_mb, parent=None):
        super().__init__(parent)
        self.source_folder = source_folder
        self.destination_folder = destination_folder
        self.size_limit_bytes = size_limit_mb * 1024 * 1024

    def _log(self, message):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.log_signal.emit(f"[{timestamp}] {message}")

    def run(self):
        folder_sizes = {}
        try:
            self._log("Memulai proses pembagian PDF...")
            self.status_signal.emit("Memvalidasi folder dan mencari file PDF...")

            if not os.path.isdir(self.source_folder):
                self._log(f"Error: Folder sumber '{self.source_folder}' tidak ditemukan atau bukan direktori.")
                self.finished_signal.emit(False, "Folder sumber tidak ditemukan.", {})
                return

            if not os.path.exists(self.destination_folder):
                os.makedirs(self.destination_folder)
                self.status_signal.emit(f"Membuat folder tujuan: {self.destination_folder}")
                self._log(f"Membuat folder tujuan: {self.destination_folder}")
            else:
                self._log(f"Folder tujuan sudah ada: {self.destination_folder}")

            pdf_files = []
            self._log(f"Mencari file PDF di '{self.source_folder}'...")
            for root, _, files in os.walk(self.source_folder):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        file_path = os.path.join(root, file)
                        try:
                            file_size = os.path.getsize(file_path)
                            pdf_files.append((file_path, file_size))
                            self._log(f"Ditemukan: '{os.path.basename(file_path)}' ({file_size / (1024 * 1024):.2f} MB)")
                        except OSError as e:
                            self._log(f"Peringatan: Gagal mendapatkan ukuran file '{os.path.basename(file_path)}': {e}. Melewatkan file ini.")

            if not pdf_files:
                self._log("Tidak ada file PDF yang ditemukan di folder sumber.")
                self.finished_signal.emit(False, "Tidak ada file PDF yang ditemukan di folder sumber.", {})
                return

            self._log(f"Total {len(pdf_files)} file PDF ditemukan.")
            self._log("Mengurutkan file berdasarkan ukuran (dari terbesar ke terkecil) untuk efisiensi...")
            pdf_files.sort(key=lambda x: x[1], reverse=True)

            current_folder_index = 1
            current_folder_size = 0
            current_folder_path = os.path.join(self.destination_folder, f"output_{current_folder_index:03d}")
            os.makedirs(current_folder_path, exist_ok=True)
            folder_sizes[current_folder_path] = 0
            self._log(f"Membuat folder output awal: {os.path.basename(current_folder_path)}")
            self.status_signal.emit(f"Mulai menyalin ke '{os.path.basename(current_folder_path)}' (0.00 MB)")

            total_files = len(pdf_files)
            processed_files = 0

            for file_path, file_size in pdf_files:
                if current_folder_size > 0 and (current_folder_size + file_size > self.size_limit_bytes):
                    current_folder_size_mb = current_folder_size / (1024 * 1024)
                    limit_mb = self.size_limit_bytes / (1024 * 1024)
                    self._log(f"Batas {limit_mb:.2f} MB tercapai untuk '{os.path.basename(current_folder_path)}'. Ukuran final folder ini: {current_folder_size_mb:.2f} MB")

                    current_folder_index += 1
                    current_folder_size = 0
                    current_folder_path = os.path.join(self.destination_folder, f"output_{current_folder_index:03d}")
                    os.makedirs(current_folder_path, exist_ok=True)
                    folder_sizes[current_folder_path] = 0
                    self._log(f"Membuat folder output baru: {os.path.basename(current_folder_path)}")
                    self.status_signal.emit(f"Pindah ke folder baru: '{os.path.basename(current_folder_path)}' (0.00 MB)")

                dest_file_path = os.path.join(current_folder_path, os.path.basename(file_path))
                try:
                    file_size_mb = file_size / (1024 * 1024)
                    self._log(f"Menyalin '{os.path.basename(file_path)}' ({file_size_mb:.2f} MB) ke '{os.path.basename(current_folder_path)}'")
                    shutil.move(file_path, dest_file_path)
                    current_folder_size += file_size
                    folder_sizes[current_folder_path] += file_size
                    self.status_signal.emit(f"Menyalin '{os.path.basename(file_path)}' ({current_folder_size / (1024 * 1024):.2f} MB)")
                except Exception as e:
                    self._log(f"Gagal menyalin '{os.path.basename(file_path)}': {e}")
                    self.status_signal.emit(f"Gagal menyalin '{os.path.basename(file_path)}'")

                processed_files += 1
                progress = int((processed_files / total_files) * 100)
                self.progress_signal.emit(progress)

            self._log("Proses pembagian PDF selesai. Melakukan verifikasi ukuran akhir folder...")
            final_folder_sizes_display = {}
            for folder_path, _ in folder_sizes.items():
                if os.path.exists(folder_path):
                    total_size_bytes_in_folder = sum(os.path.getsize(os.path.join(folder_path, f))
                                                     for f in os.listdir(folder_path)
                                                     if os.path.isfile(os.path.join(folder_path, f)))
                    final_folder_sizes_display[os.path.basename(folder_path)] = total_size_bytes_in_folder
                else:
                    final_folder_sizes_display[os.path.basename(folder_path)] = 0

            self._log("Semua file telah diproses.")
            self.finished_signal.emit(True, "Pembagian file PDF selesai!", final_folder_sizes_display)

        except Exception as e:
            self._log(f"Terjadi kesalahan fatal selama proses: {e}")
            self.finished_signal.emit(False, f"Terjadi kesalahan: {e}", {})

# --- (Bagian PdfSplitterApp tanpa tombol batal) ---
class PdfSplitterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF File Splitter")
        self.setGeometry(100, 100, 600, 400) # Ukuran jendela diperbesar sedikit untuk estetika tema gelap

        self.source_folder = ""
        self.destination_folder = ""
        self.splitter_thread = None

        self.init_ui()

    def init_ui(self):
        # Menerapkan stylesheet global untuk tema gelap pada jendela utama
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a; /* Latar belakang sangat gelap */
                color: #e0e0e0; /* Warna teks terang */
                font-family: 'Segoe UI', Arial, sans-serif; /* Font yang lebih modern */
                font-size: 12px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit {
                background-color: #2b2b2b; /* Warna input sedikit lebih terang dari latar belakang */
                border: 1px solid #444444; /* Border sedikit lebih gelap */
                color: #e0e0e0;
                padding: 6px; /* Padding sedikit lebih besar */
                border-radius: 4px; /* Sudut lebih membulat */
            }
            QPushButton {
                background-color: #007acc; /* Biru cerah, umum di tema gelap */
                color: white;
                border: none;
                padding: 10px 18px; /* Padding lebih besar */
                border-radius: 5px;
                font-size: 10px;
                font-weight: bold; /* Teks tombol lebih tebal */
            }
            QPushButton:hover {
                background-color: #005f99; /* Sedikit lebih gelap saat hover */
            }
            QPushButton:pressed {
                background-color: #004c7f; /* Lebih gelap saat ditekan */
            }
            QPushButton:disabled {
                background-color: #333333; /* Warna gelap untuk tombol nonaktif */
                color: #777777; /* Teks abu-abu untuk tombol nonaktif */
            }
            QTextEdit {
                background-color: #2b2b2b;
                color: #c0c0c0; /* Warna teks log sedikit lebih redup */
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
            }
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                border: 1px solid #3a3a3a; /* Border scrollbar */
                background: #2b2b2b; /* Latar belakang scrollbar */
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555; /* Handle scrollbar */
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: 1px solid #3a3a3a;
                background: #2b2b2b;
                height: 10px;
                subcontrol-origin: margin;
                subcontrol-position: bottom;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: #e0e0e0; /* Warna panah */
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            /* Stylesheet untuk QProgressBar */
            QProgressBar {
                border: 2px solid #444444;
                border-radius: 5px;
                background-color: #2b2b2b;
                text-align: center;
                color: #e0e0e0;
                height: 25px;
            }

            QProgressBar::chunk {
                background-color: #6c5ce7; /* Warna progress bar yang cerah */
                width: 20px;
                margin: 0.5px;
                border-radius: 3px;
            }
            /* Styling untuk QMessageBox */
            QMessageBox {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
            }
            QMessageBox QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
            }
            QMessageBox QPushButton:hover {
                background-color: #005f99;
            }
        """)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- Bagian Pilihan Folder Sumber ---
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("<b>Folder Sumber PDF:</b>"))
        self.source_path_display = QLineEdit()
        self.source_path_display.setReadOnly(True)
        self.source_path_display.setPlaceholderText("Pilih folder yang berisi file PDF...")
        source_layout.addWidget(self.source_path_display)
        self.source_button = QPushButton("Pilih Folder")
        self.source_button.clicked.connect(self.select_source_folder)
        source_layout.addWidget(self.source_button)
        main_layout.addLayout(source_layout)

        # --- Bagian Pilihan Folder Tujuan ---
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("<b>Folder Tujuan Output:</b>"))
        self.dest_path_display = QLineEdit()
        self.dest_path_display.setReadOnly(True)
        self.dest_path_display.setPlaceholderText("Pilih folder untuk menyimpan output...")
        self.dest_button = QPushButton("Pilih Folder")
        self.dest_button.clicked.connect(self.select_destination_folder)
        dest_layout.addWidget(self.dest_path_display)
        dest_layout.addWidget(self.dest_button)
        main_layout.addLayout(dest_layout)

        # --- Batas Ukuran Input ---
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("<b>Batas Ukuran Per Folder (MB):</b>"))
        self.size_input = QLineEdit()
        self.size_input.setText("100")
        self.size_input.setValidator(QIntValidator(1, 10000, self))
        self.size_input.setMaximumWidth(100)
        size_layout.addWidget(self.size_input)
        size_layout.addStretch()
        main_layout.addLayout(size_layout)

        # --- Tombol Mulai ---
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Mulai Pembagian PDF")
        self.start_button.clicked.connect(self.start_splitting)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745; /* Warna hijau untuk tombol start */
                color: white;
                border: none;
                padding: 12px 20px; /* Padding lebih besar untuk tombol utama */
                border-radius: 6px; /* Sudut lebih membulat */
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #444;
                color: #888;
            }
        """)
        button_layout.addWidget(self.start_button)
        main_layout.addLayout(button_layout)

        # --- Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.progress_bar)

        # --- Label Status ---
        self.status_label = QLabel("Siap untuk memulai...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: bold; color: #a0a0a0; margin-top: 5px; margin-bottom: 5px;")
        main_layout.addWidget(self.status_label)

        # --- Area Log Display ---
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("Log proses akan muncul di sini...")
        self.log_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        log_scroll_area = QScrollArea()
        log_scroll_area.setWidgetResizable(True)
        log_scroll_area.setWidget(self.log_display)
        main_layout.addWidget(log_scroll_area)

        self.update_start_button_state()

    # --- Metode Pembantu UI (sama seperti sebelumnya) ---

    def select_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Sumber PDF", self.source_folder if self.source_folder else os.path.expanduser("~"))
        if folder:
            self.source_folder = folder
            self.source_path_display.setText(folder)
            self.update_start_button_state()

    def select_destination_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Tujuan Output", self.destination_folder if self.destination_folder else os.path.expanduser("~"))
        if folder:
            self.destination_folder = folder
            self.dest_path_display.setText(folder)
            self.update_start_button_state()

    def update_start_button_state(self):
        is_ready = bool(self.source_folder and self.destination_folder and self.size_input.text())
        self.start_button.setEnabled(is_ready)

    def append_log(self, message):
        self.log_display.append(message)
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    # --- Metode Logika Utama (tanpa pembatalan) ---

    def start_splitting(self):
        try:
            size_limit_text = self.size_input.text()
            if not size_limit_text:
                QMessageBox.warning(self, "Input Error", "Batas ukuran tidak boleh kosong.")
                return

            size_limit_mb = int(size_limit_text)
            if size_limit_mb <= 0:
                QMessageBox.warning(self, "Input Error", "Batas ukuran harus lebih besar dari 0 MB.")
                return

            if os.path.abspath(self.source_folder) == os.path.abspath(self.destination_folder):
                reply = QMessageBox.question(self, 'Peringatan Folder',
                                             "Folder sumber dan tujuan sama. Ini dapat menimpa atau mengganggu file asli. Lanjutkan?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    return

            self.log_display.clear()
            self.append_log("--- Memulai Sesi Baru ---")
            self.append_log(f"Folder Sumber: {self.source_folder}")
            self.append_log(f"Folder Tujuan: {self.destination_folder}")
            self.append_log(f"Batas Ukuran Per Folder: {size_limit_mb} MB")

            self.start_button.setEnabled(False)
            self.source_button.setEnabled(False)
            self.dest_button.setEnabled(False)
            self.size_input.setReadOnly(True)
            self.status_label.setText("Memulai proses pembagian...")
            self.progress_bar.setValue(0)

            self.splitter_thread = PdfSplitterThread(
                self.source_folder, self.destination_folder, size_limit_mb
            )
            self.splitter_thread.progress_signal.connect(self.progress_bar.setValue)
            self.splitter_thread.status_signal.connect(self.status_label.setText)
            self.splitter_thread.log_signal.connect(self.append_log)
            self.splitter_thread.finished_signal.connect(self.on_splitting_finished)
            self.splitter_thread.start()

        except ValueError:
            QMessageBox.warning(self, "Input Error", "Batas ukuran harus berupa angka integer yang valid.")
            self.update_start_button_state()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Terjadi kesalahan yang tidak terduga saat memulai: {e}")
            self.on_splitting_finished(False, f"Error tak terduga: {e}", {})

    def on_splitting_finished(self, success, message, folder_sizes):
        if success:
            QMessageBox.information(self, "Selesai", message)
            self.status_label.setText("Pembagian file PDF selesai!")
            self.append_log("--- Pembagian Selesai ---")
            self.append_log("Ukuran Akhir Setiap Folder:")
            if folder_sizes:
                # Mengurutkan berdasarkan nomor folder
                sorted_folder_sizes = sorted(folder_sizes.items(), key=lambda item: int(item[0].split('_')[-1]))
                for folder_name, size_bytes in sorted_folder_sizes:
                    size_mb = size_bytes / (1024 * 1024)
                    self.append_log(f"  - {folder_name}: {size_mb:.2f} MB")
            else:
                self.append_log("  Tidak ada folder output yang dibuat atau informasi ukuran tidak tersedia.")
        else:
            QMessageBox.critical(self, "Gagal", message)
            self.status_label.setText(f"Gagal: {message}")
            self.append_log(f"--- Proses Gagal: {message} ---")

        self.start_button.setEnabled(True)
        self.source_button.setEnabled(True)
        self.dest_button.setEnabled(True)
        self.size_input.setReadOnly(False)
        self.update_start_button_state()

        self.splitter_thread = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PdfSplitterApp()
    window.show()
    sys.exit(app.exec())
