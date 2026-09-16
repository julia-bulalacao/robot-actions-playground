import re
import sys
from pathlib import Path


# ============================================================
# QA-A CODE QUALITY CONFIGURATION
# ============================================================

ALLOWED_LOCATOR_PREFIXES = (
    "btn_",
    "txt_",
    "dt_",
    "lnk_",
    "chk_",
    "rdo_",
    "ddl_",
    "lbl_",
    "icn_",
    "img_",
    "tbl_",
    "div_",
    "modal_",
)

MAX_SLEEP_SECONDS = 5

errors = []
warnings = []


# ============================================================
# ISSUE HANDLING
# ============================================================

def add_error(file, line_number, rule_id, title, message):
    errors.append({
        "file": str(file),
        "line": line_number,
        "rule_id": rule_id,
        "title": title,
        "message": message,
    })


def add_warning(file, line_number, rule_id, title, message):
    warnings.append({
        "file": str(file),
        "line": line_number,
        "rule_id": rule_id,
        "title": title,
        "message": message,
    })


# ============================================================
# DIFF HANDLING
# ============================================================

def parse_changed_lines(diff_file):
    """
    Parse a Git diff and return only genuinely changed NEW-side
    Robot Framework line numbers.

    Special handling:
    If an existing file had no newline at EOF, Git may show the old
    last line as removed and re-added when a developer simply presses
    Enter and adds a new line after it.

    Example:

        -    Sleep    10s
        \\ No newline at end of file
        +    Sleep    10s
        +    Log    New valid change

    In that case, the re-added Sleep line is NOT treated as changed.
    Only the genuinely new Log line is checked.
    """

    changed_lines = {}
    current_file = None
    current_hunk = []

    diff_content = Path(diff_file).read_text(
        encoding="utf-8",
        errors="replace",
    )

    def normalize_for_comparison(content):
        """
        Compare re-added EOF lines while ignoring whitespace at EOL only.
        Internal Robot Framework spacing is preserved.
        """
        return content.rstrip(" \t\r\n")
