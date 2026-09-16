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
# HELPER FUNCTIONS
# ============================================================

def get_robot_cells(line):
    """
    Split a Robot Framework line using 2+ spaces or tabs.

    Example:

    TC_001_TS_001 - Open Module    ${argument}

    becomes:

    [
        "TC_001_TS_001 - Open Module",
        "${argument}"
    ]
    """

    stripped = line.strip()

    if not stripped:
        return []

    return re.split(r"\s{2,}|\t+", stripped)


def get_test_case_id(test_case_name):
    """
    Extract TC ID from a test case name.

    Example:
    TC_001 - Proceed to ePayments
        -> TC_001
    """

    match = re.match(
        r"^(TC_\d+)\s*-\s*.+$",
        test_case_name,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return None


def get_test_step_id(test_step_name):
    """
    Extract TC and TS IDs from a test step.

    Example:
    TC_001_TS_002 - Select Mode of Payment
        -> TC_001
        -> TS_002
    """

    match = re.match(
        r"^(TC_\d+)_TS_(\d+)\s*-\s*.+$",
        test_step_name,
        re.IGNORECASE,
    )

    if match:
        return {
            "tc_id": match.group(1).upper(),
            "ts_number": match.group(2),
        }

    return None


# ============================================================
# UNIVERSAL QA-A CHECKS
# ============================================================

def check_universal_rules(file, line_number, line):
    """
    Rules that apply to both .robot and .resource files.
    """

    stripped_line = line.strip()

    if not stripped_line or stripped_line.startswith("#"):
        return

    # --------------------------------------------------------
    # QA-A001 — LOCATOR NAMING VIOLATION
    # --------------------------------------------------------

    variable_match = re.search(r"\$\{([^}]+)\}", line)

    if variable_match:
        variable_name = variable_match.group(1)

        contains_locator = re.search(
            r"(xpath=|id=|name=|css=|=//|(?<!xpath=)//)",
            line,
            re.IGNORECASE,
        )

        if contains_locator:
            if not variable_name.lower().startswith(
                ALLOWED_LOCATOR_PREFIXES
            ):
                add_error(
                    file,
                    line_number,
                    "QA-A001",
                    "Locator Naming Violation",
                    (
                        f"'${{{variable_name}}}' does not use an "
                        f"approved locator prefix."
                    ),
                )

    # --------------------------------------------------------
    # QA-A002 — INVALID XPATH FORMAT
    # --------------------------------------------------------

    if "=//" in line and "xpath=//" not in line.lower():
        add_error(
            file,
            line_number,
            "QA-A002",
            "Invalid XPath Format",
            "XPath locator must explicitly use 'xpath=//'.",
        )

    # --------------------------------------------------------
    # QA-A003 — SLEEP DURATION VIOLATION
    # --------------------------------------------------------

    sleep_match = re.search(
        r"\bSleep\s+(\d+(?:\.\d+)?)\s*"
        r"(s|sec|secs|second|seconds)?\b",
        line,
        re.IGNORECASE,
    )

    if sleep_match:
        duration = float(sleep_match.group(1))

        if duration > MAX_SLEEP_SECONDS:
            add_error(
                file,
                line_number,
                "QA-A003",
                "Sleep Duration Violation",
                (
                    f"Sleep is {duration:g}s. "
                    f"Maximum allowed duration is "
                    f"{MAX_SLEEP_SECONDS} seconds. "
                    f"Consider using an explicit wait."
                ),
            )


# ============================================================
# TEST CASE STRUCTURE CHECKS
# ============================================================

def check_test_cases(file, lines):
    """
    Check QA-A test case and test step structure.

    These rules apply only inside the:
    *** Test Cases ***

    section of .robot files.
    """

    current_section = None
    current_test_case = None
    current_test_case_id = None

    for line_number, line in enumerate(lines, start=1):

        stripped = line.strip()

        # ----------------------------------------------------
        # Detect Robot Framework section
        # ----------------------------------------------------

        section_match = re.match(
            r"^\*{3}\s*(.+?)\s*\*{3}$",
            stripped,
        )

        if section_match:
            current_section = section_match.group(1).strip().lower()
            current_test_case = None
            current_test_case_id = None
            continue

        # Only inspect Test Cases
        if current_section not in ("test cases", "tasks"):
            continue

        # Ignore empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # ----------------------------------------------------
        # Test case headers are not indented
        # ----------------------------------------------------

        is_indented = (
            line.startswith(" ")
            or line.startswith("\t")
        )

        if not is_indented:

            current_test_case = stripped
            current_test_case_id = get_test_case_id(
                current_test_case
            )

            # ------------------------------------------------
            # QA-A006 — INVALID TEST CASE NAMING
            # ------------------------------------------------

            if current_test_case_id is None:
                add_warning(
                    file,
                    line_number,
                    "QA-A006",
                    "Invalid Test Case Naming",
                    (
                        f"Test case '{current_test_case}' does not "
                        f"follow the expected QA-A naming format. "
                        f"Expected: TC_### - <Test Case Description>"
                    ),
                )

            continue

        # No active test case
        if current_test_case is None:
            continue

        cells = get_robot_cells(line)

        if not cells:
            continue

        first_cell = cells[0]

        # ----------------------------------------------------
        # Ignore Robot Framework settings inside a test case
        #
        # Example:
        # [Documentation]
        # [Tags]
        # [Setup]
        # [Teardown]
        # [Template]
        # [Timeout]
        # ----------------------------------------------------

        if first_cell.startswith("[") and first_cell.endswith("]"):
            continue

        # ----------------------------------------------------
        # QA-A004 — INVALID TEST STEP STRUCTURE
        # ----------------------------------------------------

        test_step = get_test_step_id(first_cell)

        if test_step is None:
            add_warning(
                file,
                line_number,
                "QA-A004",
                "Invalid Test Step Structure",
                (
                    f"Test step '{first_cell}' does not follow the "
                    f"expected QA-A test step format. "
                    f"Expected: TC_###_TS_### - "
                    f"<Test Step Description>"
                ),
            )
            continue

        # ----------------------------------------------------
        # QA-A005 — TEST STEP ID MISMATCH
        # ----------------------------------------------------

        if (
            current_test_case_id is not None
            and test_step["tc_id"] != current_test_case_id
        ):
            add_warning(
                file,
                line_number,
                "QA-A005",
                "Test Step ID Mismatch",
                (
                    f"Test step '{first_cell}' belongs to "
                    f"{test_step['tc_id']}, but it is currently "
                    f"under {current_test_case_id}. "
                    f"Expected prefix: "
                    f"{current_test_case_id}_TS_"
                ),
            )


# ============================================================
# FILE CHECK
# ============================================================

def check_file(file):
    content = file.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Universal checks
    for line_number, line in enumerate(lines, start=1):
        check_universal_rules(
            file,
            line_number,
            line,
        )

    # TC / TS checks only make sense for .robot files
    if file.suffix.lower() == ".robot":
        check_test_cases(file, lines)


# ============================================================
# FIND ROBOT FRAMEWORK FILES
# ============================================================

robot_files = list(Path(".").rglob("*.robot"))
robot_files += list(Path(".").rglob("*.resource"))


print("Running QA-A Code Quality checks...")
print(f"Found {len(robot_files)} Robot Framework file(s).")
print()


# ============================================================
# RUN CHECKS
# ============================================================

for robot_file in robot_files:
    check_file(robot_file)


# ============================================================
# DISPLAY ISSUES
# ============================================================

def print_issue(issue, severity):
    full_title = (
        f"{issue['rule_id']} - {issue['title']}"
    )

    github_command = (
        "error"
        if severity == "ERROR"
        else "warning"
    )

    # GitHub annotation
    print(
        f"::{github_command} "
        f"file={issue['file']},"
        f"line={issue['line']},"
        f"title={full_title}::"
        f"{full_title}: {issue['message']}"
    )

    # Human-readable output
    print(f"   Rule: {full_title}")
    print(f"   File: {issue['file']}")
    print(f"   Line: {issue['line']}")
    print(f"   Issue: {issue['message']}")
    print()


# ============================================================
# RESULTS
# ============================================================

if errors or warnings:

    print("=" * 70)
    print("QA-A CODE QUALITY RESULTS")
    print("=" * 70)
    print()

    if errors:
        print("ERRORS")
        print("-" * 70)
        print()

        for error in errors:
            print_issue(error, "ERROR")

    if warnings:
        print("WARNINGS")
        print("-" * 70)
        print()

        for warning in warnings:
            print_issue(warning, "WARNING")


print("=" * 70)
print(
    f"Summary: {len(errors)} error(s), "
    f"{len(warnings)} warning(s)"
)
print("=" * 70)


# Only ERRORS fail GitHub Actions.
if errors:
    print("QA-A Code Quality FAILED.")
    sys.exit(1)


if warnings:
    print(
        "QA-A Code Quality PASSED with warnings. "
        "Review the recommendations above."
    )
    sys.exit(0)


print("QA-A Code Quality PASSED.")
print("No QA-A code quality violations found.")

sys.exit(0)