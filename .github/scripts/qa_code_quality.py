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
    Parse a Git diff and return:

    {
        "tests/sample.robot": {12, 13, 20},
        "resource/variables.resource": {5, 6}
    }

    Only NEW-side line numbers are recorded.
    """

    changed_lines = {}

    current_file = None

    diff_content = Path(diff_file).read_text(
        encoding="utf-8",
        errors="replace",
    )

    for line in diff_content.splitlines():

        # Example:
        # +++ b/tests/sample.robot
        if line.startswith("+++ b/"):
            current_file = line[6:]

            if current_file.endswith(
                (".robot", ".resource")
            ):
                changed_lines.setdefault(
                    current_file,
                    set(),
                )
            else:
                current_file = None

            continue

        # Example:
        # @@ -10,0 +11,2 @@
        #
        # We only care about the NEW side:
        # +11,2
        if current_file and line.startswith("@@"):

            match = re.search(
                r"\+(\d+)(?:,(\d+))?",
                line,
            )

            if not match:
                continue

            start_line = int(match.group(1))

            line_count = (
                int(match.group(2))
                if match.group(2)
                else 1
            )

            # A count of 0 means no lines exist
            # on the new side of this hunk.
            if line_count == 0:
                continue

            for line_number in range(
                start_line,
                start_line + line_count,
            ):
                changed_lines[current_file].add(
                    line_number
                )

    return changed_lines


def is_changed_line(
    file,
    line_number,
    changed_lines,
):
    """
    Return True when the line should be reported.

    If changed_lines is None, the script is running
    in full-scan/local mode.
    """

    if changed_lines is None:
        return True

    file_key = str(file).replace("\\", "/")

    return (
        file_key in changed_lines
        and line_number in changed_lines[file_key]
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_robot_cells(line):

    stripped = line.strip()

    if not stripped:
        return []

    return re.split(
        r"\s{2,}|\t+",
        stripped,
    )


def get_test_case_id(test_case_name):

    match = re.match(
        r"^(TC_\d+)\s*-\s*.+$",
        test_case_name,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return None


def get_test_step_id(test_step_name):

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

def check_universal_rules(
    file,
    line_number,
    line,
    changed_lines,
):

    # Do not report universal-rule violations
    # from untouched lines.
    if not is_changed_line(
        file,
        line_number,
        changed_lines,
    ):
        return

    stripped_line = line.strip()

    if (
        not stripped_line
        or stripped_line.startswith("#")
    ):
        return

    # --------------------------------------------------------
    # QA-A001 — LOCATOR NAMING VIOLATION
    # --------------------------------------------------------

    variable_match = re.search(
        r"\$\{([^}]+)\}",
        line,
    )

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
                        f"'${{{variable_name}}}' does not use "
                        f"an approved locator prefix."
                    ),
                )

    # --------------------------------------------------------
    # QA-A002 — INVALID XPATH FORMAT
    # --------------------------------------------------------

    if (
        "=//" in line
        and "xpath=//" not in line.lower()
    ):
        add_error(
            file,
            line_number,
            "QA-A002",
            "Invalid XPath Format",
            (
                "XPath locator must explicitly "
                "use 'xpath=//'."
            ),
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

        duration = float(
            sleep_match.group(1)
        )

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

def check_test_cases(
    file,
    lines,
    changed_lines,
):

    current_section = None
    current_test_case = None
    current_test_case_id = None

    for line_number, line in enumerate(
        lines,
        start=1,
    ):

        stripped = line.strip()

        # ----------------------------------------------------
        # Detect Robot Framework section
        # ----------------------------------------------------

        section_match = re.match(
            r"^\*{3}\s*(.+?)\s*\*{3}$",
            stripped,
        )

        if section_match:

            current_section = (
                section_match
                .group(1)
                .strip()
                .lower()
            )

            current_test_case = None
            current_test_case_id = None

            continue

        if current_section not in (
            "test cases",
            "tasks",
        ):
            continue

        if (
            not stripped
            or stripped.startswith("#")
        ):
            continue

        is_indented = (
            line.startswith(" ")
            or line.startswith("\t")
        )

        # ----------------------------------------------------
        # TEST CASE HEADER
        # ----------------------------------------------------

        if not is_indented:

            current_test_case = stripped

            current_test_case_id = (
                get_test_case_id(
                    current_test_case
                )
            )

            # QA-A006 only reports if the actual
            # test case header was changed.
            if (
                current_test_case_id is None
                and is_changed_line(
                    file,
                    line_number,
                    changed_lines,
                )
            ):
                add_warning(
                    file,
                    line_number,
                    "QA-A006",
                    "Invalid Test Case Naming",
                    (
                        f"Test case "
                        f"'{current_test_case}' does not "
                        f"follow the expected QA-A naming "
                        f"format. Expected: "
                        f"TC_### - "
                        f"<Test Case Description>"
                    ),
                )

            continue

        if current_test_case is None:
            continue

        cells = get_robot_cells(line)

        if not cells:
            continue

        first_cell = cells[0]

        # Ignore Robot Framework settings
        if (
            first_cell.startswith("[")
            and first_cell.endswith("]")
        ):
            continue

        # Important:
        # We parsed the entire file to understand
        # the current Test Case, but only changed
        # test-step lines are reportable.
        if not is_changed_line(
            file,
            line_number,
            changed_lines,
        ):
            continue

        # ----------------------------------------------------
        # QA-A004 — INVALID TEST STEP STRUCTURE
        # ----------------------------------------------------

        test_step = get_test_step_id(
            first_cell
        )

        if test_step is None:
            add_warning(
                file,
                line_number,
                "QA-A004",
                "Invalid Test Step Structure",
                (
                    f"Test step '{first_cell}' does not "
                    f"follow the expected QA-A test "
                    f"step format. Expected: "
                    f"TC_###_TS_### - "
                    f"<Test Step Description>"
                ),
            )

            continue

        # ----------------------------------------------------
        # QA-A005 — TEST STEP ID MISMATCH
        # ----------------------------------------------------

        if (
            current_test_case_id is not None
            and test_step["tc_id"]
            != current_test_case_id
        ):
            add_warning(
                file,
                line_number,
                "QA-A005",
                "Test Step ID Mismatch",
                (
                    f"Test step '{first_cell}' belongs "
                    f"to {test_step['tc_id']}, but it "
                    f"is currently under "
                    f"{current_test_case_id}. "
                    f"Expected prefix: "
                    f"{current_test_case_id}_TS_"
                ),
            )


# ============================================================
# FILE CHECK
# ============================================================

def check_file(
    file,
    changed_lines,
):

    content = file.read_text(
        encoding="utf-8"
    )

    lines = content.splitlines()

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        check_universal_rules(
            file,
            line_number,
            line,
            changed_lines,
        )

    if file.suffix.lower() == ".robot":
        check_test_cases(
            file,
            lines,
            changed_lines,
        )


# ============================================================
# DETERMINE EXECUTION MODE
# ============================================================

changed_lines = None


if (
    len(sys.argv) == 3
    and sys.argv[1] == "--diff"
):

    diff_file = sys.argv[2]

    changed_lines = parse_changed_lines(
        diff_file
    )

    robot_files = []

    for file_name in changed_lines:

        path = Path(file_name)

        if (
            path.exists()
            and path.is_file()
        ):
            robot_files.append(path)

    mode = "Changed Robot Framework lines only"

else:

    robot_files = list(
        Path(".").rglob("*.robot")
    )

    robot_files += list(
        Path(".").rglob("*.resource")
    )

    mode = "Full repository scan"


# ============================================================
# RUN CHECKS
# ============================================================

print(
    "Running QA-A Code Quality checks..."
)

print(f"Mode: {mode}")

print(
    f"Checking {len(robot_files)} "
    f"Robot Framework file(s)."
)

print()


for robot_file in robot_files:

    print(f"  - {robot_file}")

    if changed_lines is not None:

        file_key = str(
            robot_file
        ).replace("\\", "/")

        line_numbers = sorted(
            changed_lines.get(
                file_key,
                set(),
            )
        )

        if line_numbers:
            print(
                "    Changed lines: "
                + ", ".join(
                    str(number)
                    for number in line_numbers
                )
            )


print()


for robot_file in robot_files:
    check_file(
        robot_file,
        changed_lines,
    )


# ============================================================
# DISPLAY ISSUES
# ============================================================

def print_issue(
    issue,
    severity,
):

    full_title = (
        f"{issue['rule_id']} - "
        f"{issue['title']}"
    )

    github_command = (
        "error"
        if severity == "ERROR"
        else "warning"
    )

    print(
        f"::{github_command} "
        f"file={issue['file']},"
        f"line={issue['line']},"
        f"title={full_title}::"
        f"{full_title}: "
        f"{issue['message']}"
    )

    print(
        f"   Rule: {full_title}"
    )
    print(
        f"   File: {issue['file']}"
    )
    print(
        f"   Line: {issue['line']}"
    )
    print(
        f"   Issue: {issue['message']}"
    )
    print()


# ============================================================
# RESULTS
# ============================================================

if errors or warnings:

    print("=" * 70)
    print(
        "QA-A CODE QUALITY RESULTS"
    )
    print("=" * 70)
    print()

    if errors:

        print("ERRORS")
        print("-" * 70)
        print()

        for error in errors:
            print_issue(
                error,
                "ERROR",
            )

    if warnings:

        print("WARNINGS")
        print("-" * 70)
        print()

        for warning in warnings:
            print_issue(
                warning,
                "WARNING",
            )


print("=" * 70)

print(
    f"Summary: {len(errors)} error(s), "
    f"{len(warnings)} warning(s)"
)

print("=" * 70)


if errors:

    print(
        "QA-A Code Quality FAILED."
    )

    sys.exit(1)


if warnings:

    print(
        "QA-A Code Quality PASSED "
        "with warnings. "
        "Review the recommendations above."
    )

    sys.exit(0)


print(
    "QA-A Code Quality PASSED."
)

print(
    "No QA-A code quality violations "
    "found in the checked lines."
)

sys.exit(0)