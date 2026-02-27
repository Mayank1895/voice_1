import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QFrame, QMessageBox, QTextEdit, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from user_management import UserManager
from verification import authenticate_speaker
from command import CommandEngine
from enrollment import enroll


# ==========================================================
# VERIFICATION THREAD
# ==========================================================
class VerificationThread(QThread):
    result_signal = pyqtSignal(object)
    message_signal = pyqtSignal(str)

    def run(self):
        self.message_signal.emit("Starting authentication...\n")
        user = authenticate_speaker()

        if user:
            self.message_signal.emit(f"Authenticated: {user['name']}\n")
        else:
            self.message_signal.emit("Authentication failed.\n")

        self.result_signal.emit(user)


# ==========================================================
# COMMAND THREAD
# ==========================================================
class CommandThread(QThread):
    finished_signal = pyqtSignal()
    message_signal = pyqtSignal(str)

    def __init__(self, user):
        super().__init__()
        self.user = user

    def run(self):
        engine = CommandEngine(message_callback=self.message_signal.emit)
        engine.start_session(self.user)
        self.finished_signal.emit()


# ==========================================================
# ENROLLMENT THREAD
# ==========================================================
class EnrollmentThread(QThread):
    finished_signal = pyqtSignal()
    message_signal = pyqtSignal(str)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def run(self):
        self.message_signal.emit(f"Enrollment started for {self.name}...\n")

        try:
            enroll(self.name, logger=self.message_signal.emit)
            self.message_signal.emit("\nEnrollment completed successfully.\n")
        except Exception as e:
            self.message_signal.emit(f"\nEnrollment failed: {str(e)}\n")

        self.finished_signal.emit()

# ==========================================================
# MAIN UI
# ==========================================================
class VoiceFailSafeUI(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Voice Fail-Safe System")
        self.setGeometry(200, 100, 1150, 720)

        self.manager = UserManager()
        self.current_user = None
        self.session_active = False

        self.init_ui()
        self.load_users()

    # ==========================================================
    # UI SETUP
    # ==========================================================
    def init_ui(self):

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Header
        header_layout = QHBoxLayout()

        self.title = QLabel("Voice Fail-Safe Control Panel")
        self.title.setFont(QFont("Segoe UI", 18))

        self.system_status = QLabel("● SYSTEM ONLINE")

        header_layout.addWidget(self.title)
        header_layout.addStretch()
        header_layout.addWidget(self.system_status)

        main_layout.addLayout(header_layout)

        # Body
        body_layout = QHBoxLayout()
        main_layout.addLayout(body_layout)

        # Sidebar
        sidebar = QVBoxLayout()

        self.user_list = QListWidget()
        sidebar.addWidget(QLabel("Enrolled Users"))
        sidebar.addWidget(self.user_list)

        self.enroll_btn = QPushButton("Enroll User")
        self.auth_btn = QPushButton("Authorize User")
        self.remove_btn = QPushButton("Remove User")

        sidebar.addWidget(self.enroll_btn)
        sidebar.addWidget(self.auth_btn)
        sidebar.addWidget(self.remove_btn)

        body_layout.addLayout(sidebar, 1)

        # Main Content
        content = QVBoxLayout()

        self.verify_box = QPushButton("Activate System")
        self.verify_box.setFixedHeight(60)

        self.status_label = QLabel("● Status: Idle")

        self.console = QTextEdit()
        self.console.setReadOnly(True)

        content.addWidget(self.verify_box)
        content.addWidget(self.status_label)
        content.addWidget(self.console)

        body_layout.addLayout(content, 2)

        # Button connections
        self.verify_box.clicked.connect(self.activate_system)
        self.enroll_btn.clicked.connect(self.enroll_user)
        self.auth_btn.clicked.connect(self.authorize_user)
        self.remove_btn.clicked.connect(self.remove_user)

    # ==========================================================
    # USER MANAGEMENT
    # ==========================================================
    def load_users(self):
        self.user_list.clear()
        users = self.manager.load_users()

        for user_id, user in users.items():
            status = "✔" if user.get("authorized") else "✖"
            display = f"{user['name']} ({user['role']}) [{status}]"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, user_id)
            self.user_list.addItem(item)

    def get_selected_user_id(self):
        selected = self.user_list.currentItem()
        if not selected:
            return None
        return selected.data(Qt.UserRole)

    def authorize_user(self):
        user_id = self.get_selected_user_id()
        if not user_id:
            QMessageBox.warning(self, "Error", "Select a user first")
            return

        success, message = self.manager.authorize_user(user_id)
        QMessageBox.information(self, "Status", message)
        self.load_users()

    def remove_user(self):
        user_id = self.get_selected_user_id()
        if not user_id:
            QMessageBox.warning(self, "Error", "Select a user first")
            return

        success, message = self.manager.remove_user(user_id)
        QMessageBox.information(self, "Status", message)
        self.load_users()

    # ==========================================================
    # ENROLL USER
    # ==========================================================
    def enroll_user(self):

        name, ok = QInputDialog.getText(
            self,
            "Enroll User",
            "Enter user name:"
        )

        if not ok or not name.strip():
            return

        name = name.strip().lower()

        self.enroll_btn.setEnabled(False)

        self.enroll_thread = EnrollmentThread(name)
        self.enroll_thread.message_signal.connect(self.append_console)
        self.enroll_thread.finished_signal.connect(self.enrollment_finished)
        self.enroll_thread.start()

    def enrollment_finished(self):
        self.load_users()
        self.enroll_btn.setEnabled(True)

    # ==========================================================
    # ACTIVATION FLOW
    # ==========================================================
    def activate_system(self):

        if self.session_active:
            QMessageBox.warning(self, "System Active", "Session already running")
            return

        self.append_console("System activation initiated...\n")
        self.status_label.setText("● Status: Verifying...")
        self.verify_box.setEnabled(False)

        self.verify_thread = VerificationThread()
        self.verify_thread.message_signal.connect(self.append_console)
        self.verify_thread.result_signal.connect(self.handle_verification)
        self.verify_thread.start()

    def handle_verification(self, user):

        if not user:
            self.status_label.setText("● Verification Failed")
            self.verify_box.setEnabled(True)
            self.append_console("Verification failed.\n")
            return

        self.current_user = user
        self.session_active = True

        self.status_label.setText(f"● Verified: {user['name']}")
        self.append_console(f"User verified: {user['name']}\n")

        self.command_thread = CommandThread(user)
        self.command_thread.message_signal.connect(self.append_console)
        self.command_thread.finished_signal.connect(self.session_finished)
        self.command_thread.start()

    def session_finished(self):
        self.append_console("Session terminated.\n")
        self.status_label.setText("● Session Ended")
        self.verify_box.setEnabled(True)
        self.session_active = False
        self.current_user = None

    # ==========================================================
    def append_console(self, message):
        self.console.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VoiceFailSafeUI()
    window.show()
    sys.exit(app.exec_())