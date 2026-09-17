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
    "row_",
    "col_",
    "div_",
    "con_",
    "modal_",
    "swal_",
    "tab_",
    "frm_",
    "ifrm_",
    "upl_",
    "lst_",
    "opt_",
    "card_",
    "nav_",
    "msg_",
    "badge_",
    "ldr_",
)

LOCATOR_VARIABLE_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
)

EXPLICIT_LOCATOR_PATTERN = re.compile(
    r"(xpath=|id=|name=|css=|=//|(?<!xpath=)//)",
    re.IGNORECASE,
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
    Parse a Git diff and return genuinely changed NEW-side line numbers.

    This also handles the missing-newline-at-EOF case. Git can show an
    unchanged old last line as removed/re-added when a developer presses
    Enter and adds new content after it. That preserved old line should
    not be treated as newly changed.
    """

    changed_lines = {}
    current_file = None
    old_line_number = None
    new_line_number = None
    current_hunk = []
    previous_change = None

    diff_content = Path(diff_file).read_text(
        encoding="utf-8",
        errors="replace",
    )

    def normalize_eof_line(content):
        # Ignore only trailing spaces/tabs for the EOF comparison.
        # Internal Robot Framework spacing remains unchanged.
        return content.rstrip(" \t\r\n")

    def process_hunk():
        if current_file is None or not current_hunk:
            return

        added_items = [
            item for item in current_hunk
            if item["type"] == "+"
        ]

        ignored_added_lines = set()

        # Suppress only an added line that exactly preserves a removed
        # old EOF line explicitly marked by Git as having no newline.
        for removed in current_hunk:
            if (
                removed["type"] != "-"
                or not removed["no_newline_at_eof"]
            ):
                continue

            old_content = normalize_eof_line(
                removed["content"]
            )

            for added in added_items:
                if added["new_line"] in ignored_added_lines:
                    continue

                if normalize_eof_line(
                    added["content"]
                ) == old_content:
                    ignored_added_lines.add(
                        added["new_line"]
                    )
                    break

        for added in added_items:
            if added["new_line"] not in ignored_added_lines:
                changed_lines.setdefault(
                    current_file,
                    set(),
                ).add(added["new_line"])

    for line in diff_content.splitlines():

        if line.startswith("diff --git "):
            process_hunk()
            current_hunk = []
            current_file = None
            old_line_number = None
            new_line_number = None
            previous_change = None
            continue

        if line.startswith("+++ b/"):
            process_hunk()
            current_hunk = []
            previous_change = None

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

        if current_file and line.startswith("@@"):
            process_hunk()
            current_hunk = []
            previous_change = None

            match = re.search(
                r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@",
                line,
            )

            if not match:
                old_line_number = None
                new_line_number = None
                continue

            old_line_number = int(match.group(1))
            new_line_number = int(match.group(2))
            continue

        if (
            current_file is None
            or old_line_number is None
            or new_line_number is None
        ):
            continue

        if line == r"\ No newline at end of file":
            if previous_change is not None:
                previous_change["no_newline_at_eof"] = True
            continue

        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        if line.startswith("+"):
            item = {
                "type": "+",
                "content": line[1:],
                "new_line": new_line_number,
                "no_newline_at_eof": False,
            }
            current_hunk.append(item)
            previous_change = item
            new_line_number += 1
            continue

        if line.startswith("-"):
            item = {
                "type": "-",
                "content": line[1:],
                "old_line": old_line_number,
                "no_newline_at_eof": False,
            }
            current_hunk.append(item)
            previous_change = item
            old_line_number += 1
            continue

        if line.startswith(" "):
            old_line_number += 1
            new_line_number += 1
            previous_change = None

    process_hunk()
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


def is_locator_variable(variable_name, line):
    """
    Determine whether a Robot Framework variable represents a locator.

    Explicit locator strategies such as xpath=, id=, name=, css=,
    and XPath expressions are always treated as locators.

    Bare/direct locator values are treated as locators when the
    variable already uses an approved locator prefix.
    """

    if EXPLICIT_LOCATOR_PATTERN.search(line):
        return True

    return variable_name.lower().startswith(
        ALLOWED_LOCATOR_PREFIXES
    )


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

        if is_locator_variable(
            variable_name,
            line,
        ):

            has_valid_prefix = variable_name.startswith(
                ALLOWED_LOCATOR_PREFIXES
            )

            is_snake_case = bool(
                LOCATOR_VARIABLE_PATTERN.fullmatch(
                    variable_name
                )
            )

            if not has_valid_prefix or not is_snake_case:

                issues = []

                if not has_valid_prefix:
                    issues.append(
                        "does not use an approved locator prefix"
                    )

                if not is_snake_case:
                    issues.append(
                        "does not follow snake_case naming"
                    )

                add_error(
                    file,
                    line_number,
                    "QA-A001",
                    "Locator Naming Violation",
                    (
                        f"'${{{variable_name}}}' "
                        + " and ".join(issues)
                        + "."
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

        # Parse the entire file to understand the current
        # Test Case, but report only changed test-step lines.
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
# GITHUB ANNOTATIONS
# ============================================================

def create_github_annotation(
    issue,
    severity,
):

    github_command = (
        "error"
        if severity == "ERROR"
        else "warning"
    )

    annotation_title = (
        f"{issue['rule_id']} - "
        f"{issue['title']}"
    )

    print(
        f"::{github_command} "
        f"file={issue['file']},"
        f"line={issue['line']},"
        f"title={annotation_title}::"
        f"{issue['message']}"
    )


for error in errors:
    create_github_annotation(
        error,
        "ERROR",
    )

for warning in warnings:
    create_github_annotation(
        warning,
        "WARNING",
    )


# ============================================================
# DISPLAY ISSUES
# ============================================================

def print_issue(issue, severity):

    full_title = (
        f"{issue['rule_id']} - "
        f"{issue['title']}"
    )

    github_command = (
        "error"
        if severity == "ERROR"
        else "warning"
    )

    # GitHub annotation.
    # This creates the highlighted Error/Warning row.
    print(
        f"::{github_command} "
        f"file={issue['file']},"
        f"line={issue['line']},"
        f"title={full_title}::"
        f"{issue['message']}"
    )

    # Additional details only.
    # Do not repeat the issue message here.
    print(f"   File : {issue['file']}")
    print(f"   Line : {issue['line']}")
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


# ============================================================
# SUMMARY
# ============================================================

print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"Errors   : {len(errors)}")
print(f"Warnings : {len(warnings)}")

if errors:
    result = "FAILED"
elif warnings:
    result = "PASSED WITH WARNINGS"
else:
    result = "PASSED"

print(f"Result   : {result}")

print("=" * 70)


# ============================================================
# EXIT STATUS
# ============================================================

if errors:
    sys.exit(1)

sys.exit(0)


# ============================================================
# RESULTS
# ============================================================

if errors or warnings:

    print()
    print("=" * 70)
    print("QA-A CODE QUALITY RESULTS")
    print("=" * 70)
    print()

    if errors:

        print("ERRORS")
        print("-" * 70)
        print()

        for error in errors:
            print_issue(error)

    if warnings:

        print("WARNINGS")
        print("-" * 70)
        print()

        for warning in warnings:
            print_issue(warning)


# ============================================================
# SUMMARY
# ============================================================

print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"Errors   : {len(errors)}")
print(f"Warnings : {len(warnings)}")

if errors:
    result = "FAILED"
elif warnings:
    result = "PASSED WITH WARNINGS"
else:
    result = "PASSED"

print(f"Result   : {result}")

print("=" * 70)


# ============================================================
# EXIT STATUS
# ============================================================

if errors:
    sys.exit(1)

sys.exit(0)