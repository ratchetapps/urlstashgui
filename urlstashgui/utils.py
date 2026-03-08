# utils.py
import re


def sanitize_for_windows(filename: str) -> str:
    # Removes non-alphanumeric characters and converts to lowercase.
    return "".join(ch for ch in filename if ch.isalnum()).lower()


def remove_dash_number_suffix(text: str) -> str:
    # Removes a trailing dash with exactly two digits.
    return re.sub(r"-\d\d$", "", text) if text else ""
