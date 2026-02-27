import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "system.log")


class SimpleLogger:

    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)

        # Create file if it doesn't exist
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w") as f:
                f.write("=== Voice Fail-Safe System Log ===\n")

    def write(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {message}\n")