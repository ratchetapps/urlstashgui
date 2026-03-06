# logger_setup.py
import logging
import re
import tkinter as tk


def redact_sensitive_data(message: str) -> str:
    redacted = message
    redacted = re.sub(
        r'([\'"]apikey[\'"]\s*:\s*[\'"])(.*?)([\'"])',
        r"\1***\3",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r'([\'"]ApiKey[\'"]\s*:\s*[\'"])(.*?)([\'"])',
        r"\1***\3",
        redacted,
    )
    redacted = re.sub(
        r"(API Key\s*[:=]\s*)(.+)",
        r"\1***",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_sensitive_data(record.getMessage())
        record.args = ()
        return True


def setup_logger(name: str, log_file: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.filters.clear()
    logger.addFilter(SensitiveDataFilter())
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


class TextHandler(logging.Handler):
    """
    Logging handler that writes log messages to a Tkinter Text widget.
    """

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record) + "\n"

        def append():
            self.text_widget.configure(state="normal")
            # Tag [JSON] messages as dark green.
            if "[JSON]" in msg:
                self.text_widget.insert(tk.END, msg, "update_complete")
            # Tag [FILE ERROR] messages as dark red.
            elif "[FILE ERROR]" in msg:
                self.text_widget.insert(tk.END, msg, "file_error")
            elif "Match found" in msg:
                self.text_widget.insert(tk.END, msg, "match_found")
            elif "Update complete" in msg:
                self.text_widget.insert(tk.END, msg, "update_complete")
            else:
                self.text_widget.insert(tk.END, msg)
            self.text_widget.configure(state="disabled")
            self.text_widget.yview(tk.END)

        self.text_widget.after(0, append)
