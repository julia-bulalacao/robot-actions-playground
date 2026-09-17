import re
import sys
from collections import defaultdict
from pathlib import Path

# ============================================================
# QA-A CODE QUALITY CONFIGURATION
# ============================================================

ALLOWED_LOCATOR_PREFIXES = (
    "btn_", "txt_", "dt_", "lnk_", "chk_", "rdo_", "ddl_", "lbl_",
    "icn_", "img_", "tbl_", "row_", "col_", "div_", "con_", "modal_",
    "swal_", "tab_", "frm_", "ifrm_", "upl_", "lst_", "opt_", "card_",
    "nav_", "msg_", "badge_", "ldr_",
)

LOCATOR_VARIABLE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
EXPLICIT_LOCATOR_PATTERN = re.compile(
    r"(xpath=|id=|name=|css=|=//|(?<![:=])//)", re.IGNORECASE
)
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
VARIABLE_TOKEN_PATTERN = re.compile(r"[$@&]\{([^}]+)\}")
ASSIGNMENT_CELL_PATTERN = re.compile(r"^[$@&]\{([^}]+)\}=?$")
SECTION_PATTERN = re.compile(r"^\*{3}\s*(.+?)\s*\*{3}$")

MAX_SLEEP_SECONDS = 5

errors = []
warnings = []

# ============================================================
# CONSOLE COLORS
# ============================================================

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"


# ============================================================
# ISSUE HANDLING
# ============================================================

def add_error(file, line_number, rule_id, title, message):
    errors.append({
        "file": str(file), "line": line_number, "rule_id": rule_id,
        "title": title, "message": message,
    })


def add_warning(file, line_number, rule_id, title, message):
    warnings.append({
        "file": str(file), "line": line_number, "rule_id": rule_id,
        "title": title, "message": message,
    })


# ============================================================
# DIFF HANDLING
# ============================================================

def parse_changed_lines(diff_file):
    """Parse a Git diff and return genuinely changed NEW-side line numbers."""
    changed_lines = {}
    current_file = None
    old_line_number = None
    new_line_number = None
    current_hunk = []
    previous_change = None

    diff_content = Path(diff_file).read_text(encoding="utf-8", errors="replace")

    def normalize_eof_line(content):
        return content.rstrip(" \t\r\n")

    def process_hunk():
        if current_file is None or not current_hunk:
            return

        added_items = [item for item in current_hunk if item["type"] == "+"]
        ignored_added_lines = set()

        for removed in current_hunk:
            if removed["type"] != "-" or not removed["no_newline_at_eof"]:
                continue
            old_content = normalize_eof_line(removed["content"])
            for added in added_items:
                if added["new_line"] in ignored_added_lines:
                    continue
                if normalize_eof_line(added["content"]) == old_content:
                    ignored_added_lines.add(added["new_line"])
                    break

        for added in added_items:
            if added["new_line"] not in ignored_added_lines:
                changed_lines.setdefault(current_file, set()).add(added["new_line"])

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
            if current_file.endswith((".robot", ".resource")):
                changed_lines.setdefault(current_file, set())
            else:
                current_file = None
            continue

        if current_file and line.startswith("@@"):
            process_hunk()
            current_hunk = []
            previous_change = None
            match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if not match:
                old_line_number = None
                new_line_number = None
                continue
            old_line_number = int(match.group(1))
            new_line_number = int(match.group(2))
            continue

        if current_file is None or old_line_number is None or new_line_number is None:
            continue

        if line == r"\ No newline at end of file":
            if previous_change is not None:
                previous_change["no_newline_at_eof"] = True
            continue

        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        if line.startswith("+"):
            item = {
                "type": "+", "content": line[1:], "new_line": new_line_number,
                "no_newline_at_eof": False,
            }
            current_hunk.append(item)
            previous_change = item
            new_line_number += 1
            continue

        if line.startswith("-"):
            item = {
                "type": "-", "content": line[1:], "old_line": old_line_number,
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


def is_changed_line(file, line_number, changed_lines):
    if changed_lines is None:
        return True
    file_key = str(file).replace("\\", "/")
    return file_key in changed_lines and line_number in changed_lines[file_key]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_robot_cells(line):
    stripped = line.strip()
    if not stripped:
        return []
    return re.split(r"\s{2,}|\t+", stripped)


def get_test_case_id(test_case_name):
    match = re.match(r"^(TC_\d+)\s*-\s*.+$", test_case_name, re.IGNORECASE)
    return match.group(1).upper() if match else None


def get_test_step_id(test_step_name):
    match = re.match(r"^(TC_\d+)_TS_(\d+)\s*-\s*.+$", test_step_name, re.IGNORECASE)
    if match:
        return {"tc_id": match.group(1).upper(), "ts_number": match.group(2)}
    return None


def is_locator_variable(variable_name, line):
    if EXPLICIT_LOCATOR_PATTERN.search(line):
        return True
    return variable_name.lower().startswith(ALLOWED_LOCATOR_PREFIXES)


def normalize_keyword_name(name):
    # Robot Framework keyword matching is case/space/underscore insensitive.
    return re.sub(r"[ _]", "", name).lower()


def normalize_keyword_body(body_lines):
    normalized = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = get_robot_cells(line)
        if not cells:
            continue
        # Ignore documentation/tags because QA-A008 compares implementation.
        if cells[0].lower() in ("[documentation]", "[tags]"):
            continue
        normalized.append(" || ".join(cell.strip() for cell in cells))
    return tuple(normalized)


def all_robot_files():
    files = list(Path(".").rglob("*.robot"))
    files += list(Path(".").rglob("*.resource"))
    return sorted(set(files))


def parse_repository(files):
    """Build a lightweight repository index for maintainability checks."""
    keyword_definitions = []
    keyword_calls = defaultdict(list)
    locator_definitions = []

    for file in files:
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        current_section = None
        current_keyword = None
        current_keyword_line = None
        current_keyword_body = []

        def finish_keyword():
            nonlocal current_keyword, current_keyword_line, current_keyword_body
            if current_keyword is not None:
                keyword_definitions.append({
                    "name": current_keyword,
                    "normalized_name": normalize_keyword_name(current_keyword),
                    "file": file,
                    "line": current_keyword_line,
                    "body": normalize_keyword_body(current_keyword_body),
                })
            current_keyword = None
            current_keyword_line = None
            current_keyword_body = []

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            section_match = SECTION_PATTERN.match(stripped)
            if section_match:
                finish_keyword()
                current_section = section_match.group(1).strip().lower()
                continue

            if not stripped or stripped.startswith("#"):
                if current_keyword is not None:
                    current_keyword_body.append(line)
                continue

            is_indented = line.startswith((" ", "\t"))

            if current_section == "keywords":
                if not is_indented:
                    finish_keyword()
                    current_keyword = stripped
                    current_keyword_line = line_number
                elif current_keyword is not None:
                    current_keyword_body.append(line)
                    cells = get_robot_cells(line)
                    if cells and not cells[0].startswith("["):
                        # Skip assignment cells to find the called keyword.
                        idx = 0
                        while idx < len(cells) and ASSIGNMENT_CELL_PATTERN.match(cells[idx]):
                            idx += 1
                        if idx < len(cells):
                            keyword_calls[normalize_keyword_name(cells[idx])].append((file, line_number))

            elif current_section in ("test cases", "tasks") and is_indented:
                cells = get_robot_cells(line)
                if cells and not cells[0].startswith("["):
                    idx = 0
                    while idx < len(cells) and ASSIGNMENT_CELL_PATTERN.match(cells[idx]):
                        idx += 1
                    if idx < len(cells):
                        keyword_calls[normalize_keyword_name(cells[idx])].append((file, line_number))

            elif current_section == "variables":
                cells = get_robot_cells(line)
                if len(cells) >= 2:
                    variable_match = re.match(r"^\$\{([^}]+)\}$", cells[0])
                    if variable_match:
                        variable_name = variable_match.group(1)
                        value = "    ".join(cells[1:])
                        if is_locator_variable(variable_name, value):
                            locator_definitions.append({
                                "name": variable_name,
                                "value": value.strip(),
                                "file": file,
                                "line": line_number,
                            })

        finish_keyword()

    return {
        "keyword_definitions": keyword_definitions,
        "keyword_calls": keyword_calls,
        "locator_definitions": locator_definitions,
    }


# ============================================================
# UNIVERSAL QA-A CHECKS
# ============================================================

def check_universal_rules(file, line_number, line, changed_lines, current_section):
    if not is_changed_line(file, line_number, changed_lines):
        return

    stripped_line = line.strip()
    if not stripped_line or stripped_line.startswith("#"):
        return

    # QA-A001 — LOCATOR NAMING VIOLATION
    variable_match = re.search(r"\$\{([^}]+)\}", line)
    if variable_match:
        variable_name = variable_match.group(1)
        if is_locator_variable(variable_name, line):
            has_valid_prefix = variable_name.startswith(ALLOWED_LOCATOR_PREFIXES)
            is_snake_case = bool(LOCATOR_VARIABLE_PATTERN.fullmatch(variable_name))
            if not has_valid_prefix or not is_snake_case:
                issues = []
                if not has_valid_prefix:
                    issues.append("does not use an approved locator prefix")
                if not is_snake_case:
                    issues.append("does not follow snake_case naming")
                add_error(
                    file, line_number, "QA-A001", "Locator Naming Violation",
                    f"'${{{variable_name}}}' " + " and ".join(issues) + ".",
                )

    # QA-A002 — INVALID XPATH FORMAT
    if "=//" in line and "xpath=//" not in line.lower():
        add_error(
            file, line_number, "QA-A002", "Invalid XPath Format",
            "XPath locator must explicitly use 'xpath=//'.",
        )

    # QA-A003 — SLEEP DURATION VIOLATION
    sleep_match = re.search(
        r"\bSleep\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds)?\b",
        line, re.IGNORECASE,
    )
    if sleep_match:
        duration = float(sleep_match.group(1))
        if duration > MAX_SLEEP_SECONDS:
            add_error(
                file, line_number, "QA-A003", "Sleep Duration Violation",
                f"Sleep is {duration:g}s. Maximum allowed duration is "
                f"{MAX_SLEEP_SECONDS} seconds. Consider using an explicit wait.",
            )

    # QA-A012 — HARDCODED ENVIRONMENT URL
    # URLs are allowed in *** Variables *** because that is the centralized definition.
    if current_section in ("test cases", "tasks", "keywords") and URL_PATTERN.search(line):
        add_error(
            file, line_number, "QA-A012", "Hardcoded Environment URL",
            "Environment URL is used directly in test/keyword logic. "
            "Define the URL in *** Variables *** or the designated environment "
            "resource/configuration file and reference it through a variable.",
        )


# ============================================================
# TEST CASE STRUCTURE CHECKS
# ============================================================

def check_test_cases(file, lines, changed_lines):
    current_section = None
    current_test_case = None
    current_test_case_id = None
    seen_step_ids = {}

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        section_match = SECTION_PATTERN.match(stripped)
        if section_match:
            current_section = section_match.group(1).strip().lower()
            current_test_case = None
            current_test_case_id = None
            seen_step_ids = {}
            continue

        if current_section not in ("test cases", "tasks"):
            continue
        if not stripped or stripped.startswith("#"):
            continue

        is_indented = line.startswith((" ", "\t"))

        if not is_indented:
            current_test_case = stripped
            current_test_case_id = get_test_case_id(current_test_case)
            seen_step_ids = {}

            if current_test_case_id is None and is_changed_line(file, line_number, changed_lines):
                add_warning(
                    file, line_number, "QA-A006", "Invalid Test Case Naming",
                    f"Test case '{current_test_case}' does not follow the expected "
                    "QA-A naming format. Expected: TC_### - <Test Case Description>",
                )
            continue

        if current_test_case is None:
            continue

        cells = get_robot_cells(line)
        if not cells:
            continue
        first_cell = cells[0]
        if first_cell.startswith("[") and first_cell.endswith("]"):
            continue

        test_step = get_test_step_id(first_cell)

        # QA-A014 — DUPLICATE TEST STEP ID
        if test_step is not None:
            step_key = f"{test_step['tc_id']}_TS_{test_step['ts_number']}"
            if step_key in seen_step_ids and is_changed_line(file, line_number, changed_lines):
                add_error(
                    file, line_number, "QA-A014", "Duplicate Test Step ID",
                    f"Test step ID '{step_key}' is already used on line "
                    f"{seen_step_ids[step_key]} under test case '{current_test_case}'. "
                    "Each test step ID must be unique within the test case.",
                )
            else:
                seen_step_ids.setdefault(step_key, line_number)

        # Existing structure rules only report changed test-step lines.
        if not is_changed_line(file, line_number, changed_lines):
            continue

        # QA-A004 — INVALID TEST STEP STRUCTURE
        if test_step is None:
            add_warning(
                file, line_number, "QA-A004", "Invalid Test Step Structure",
                f"Test step '{first_cell}' does not follow the expected QA-A test "
                "step format. Expected: TC_###_TS_### - <Test Step Description>",
            )
            continue

        # QA-A005 — TEST STEP ID MISMATCH
        if current_test_case_id is not None and test_step["tc_id"] != current_test_case_id:
            add_warning(
                file, line_number, "QA-A005", "Test Step ID Mismatch",
                f"Test step '{first_cell}' belongs to {test_step['tc_id']}, but it "
                f"is currently under {current_test_case_id}. Expected prefix: "
                f"{current_test_case_id}_TS_",
            )


# ============================================================
# MAINTAINABILITY CHECKS
# ============================================================

def check_unused_keywords(repo_index, changed_lines):
    """QA-A007 — report user keywords with no call anywhere in the repository."""
    calls = repo_index["keyword_calls"]
    for definition in repo_index["keyword_definitions"]:
        # In diff mode, report only newly/changed keyword definitions.
        if not is_changed_line(definition["file"], definition["line"], changed_lines):
            continue
        if definition["normalized_name"] not in calls:
            add_warning(
                definition["file"], definition["line"],
                "QA-A007", "Unused Keyword",
                f"Keyword '{definition['name']}' is defined but no usage was found "
                "in any .robot or .resource file in the repository.",
            )


def check_duplicate_keyword_implementations(repo_index, changed_lines):
    """QA-A008 — exact normalized implementation duplicated under different keywords."""
    groups = defaultdict(list)
    for definition in repo_index["keyword_definitions"]:
        if definition["body"]:
            groups[definition["body"]].append(definition)

    for definitions in groups.values():
        if len(definitions) < 2:
            continue
        for definition in definitions:
            if not is_changed_line(definition["file"], definition["line"], changed_lines):
                continue
            others = [d for d in definitions if d is not definition]
            other_text = "; ".join(
                f"'{d['name']}' ({d['file']}:{d['line']})" for d in others[:3]
            )
            add_warning(
                definition["file"], definition["line"],
                "QA-A008", "Duplicate Keyword Implementation",
                f"Keyword '{definition['name']}' has the same normalized implementation "
                f"as {other_text}. Consider consolidating the duplicated logic.",
            )


def check_unused_variables(file, lines, changed_lines):
    """QA-A009 — assigned local variables that are not referenced later in the same block."""
    current_section = None
    current_block = None
    assignments = []
    usages = defaultdict(list)

    def finish_block():
        nonlocal assignments, usages
        for assignment in assignments:
            if not is_changed_line(file, assignment["line"], changed_lines):
                continue
            later_usages = [n for n in usages[assignment["name"]] if n > assignment["line"]]
            if not later_usages:
                add_warning(
                    file, assignment["line"], "QA-A009", "Unused Variable",
                    f"Variable '${{{assignment['name']}}}' is assigned but is not used "
                    "later in the same test case or keyword.",
                )
        assignments = []
        usages = defaultdict(list)

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        section_match = SECTION_PATTERN.match(stripped)
        if section_match:
            finish_block()
            current_section = section_match.group(1).strip().lower()
            current_block = None
            continue

        if current_section not in ("test cases", "tasks", "keywords"):
            continue
        if not stripped or stripped.startswith("#"):
            continue

        is_indented = line.startswith((" ", "\t"))
        if not is_indented:
            finish_block()
            current_block = stripped
            continue
        if current_block is None:
            continue

        cells = get_robot_cells(line)
        if not cells:
            continue

        assignment_names = []
        idx = 0
        while idx < len(cells):
            match = ASSIGNMENT_CELL_PATTERN.match(cells[idx])
            if not match:
                break
            assignment_names.append(match.group(1))
            idx += 1

        for name in assignment_names:
            assignments.append({"name": name, "line": line_number})

        # Count variable references outside the assignment cells.
        remainder = "    ".join(cells[idx:])
        for name in VARIABLE_TOKEN_PATTERN.findall(remainder):
            usages[name].append(line_number)

    finish_block()


def check_duplicate_locator_definitions(repo_index, changed_lines):
    """QA-A010 — different locator variables resolving to the same literal locator."""
    groups = defaultdict(list)
    for locator in repo_index["locator_definitions"]:
        normalized_value = re.sub(r"\s+", " ", locator["value"].strip()).lower()
        groups[normalized_value].append(locator)

    for locators in groups.values():
        unique_names = {loc["name"].lower() for loc in locators}
        if len(locators) < 2 or len(unique_names) < 2:
            continue

        for locator in locators:
            if not is_changed_line(locator["file"], locator["line"], changed_lines):
                continue
            others = [loc for loc in locators if loc["name"].lower() != locator["name"].lower()]
            other_text = "; ".join(
                f"${{{loc['name']}}} ({loc['file']}:{loc['line']})" for loc in others[:3]
            )
            add_warning(
                locator["file"], locator["line"],
                "QA-A010", "Duplicate Locator Definition",
                f"Locator '${{{locator['name']}}}' uses the same locator value as "
                f"{other_text}. Consider reusing a single locator variable where appropriate.",
            )


# ============================================================
# FILE CHECK
# ============================================================

def check_file(file, changed_lines):
    content = file.read_text(encoding="utf-8")
    lines = content.splitlines()

    current_section = None
    for line_number, line in enumerate(lines, start=1):
        section_match = SECTION_PATTERN.match(line.strip())
        if section_match:
            current_section = section_match.group(1).strip().lower()
        check_universal_rules(file, line_number, line, changed_lines, current_section)

    check_unused_variables(file, lines, changed_lines)

    if file.suffix.lower() == ".robot":
        check_test_cases(file, lines, changed_lines)


# ============================================================
# DETERMINE EXECUTION MODE
# ============================================================

changed_lines = None
repo_files = all_robot_files()

if len(sys.argv) == 3 and sys.argv[1] == "--diff":
    diff_file = sys.argv[2]
    changed_lines = parse_changed_lines(diff_file)
    robot_files = []
    for file_name in changed_lines:
        path = Path(file_name)
        if path.exists() and path.is_file():
            robot_files.append(path)
    mode = "Changed Robot Framework lines only"
else:
    robot_files = repo_files
    mode = "Full repository scan"

# ============================================================
# RUN CHECKS
# ============================================================

print("Running QA-A Code Quality checks...")
print(f"Mode: {mode}")
print(f"Checking {len(robot_files)} Robot Framework file(s).")
print()

for robot_file in robot_files:
    print(f"  - {robot_file}")
    if changed_lines is not None:
        file_key = str(robot_file).replace("\\", "/")
        line_numbers = sorted(changed_lines.get(file_key, set()))
        if line_numbers:
            print("    Changed lines: " + ", ".join(str(number) for number in line_numbers))

print()

# Repository-wide index lets maintainability rules compare changed code
# against existing code without reporting unrelated old violations in diff mode.
repo_index = parse_repository(repo_files)

for robot_file in robot_files:
    check_file(robot_file, changed_lines)

check_unused_keywords(repo_index, changed_lines)
check_duplicate_keyword_implementations(repo_index, changed_lines)
check_duplicate_locator_definitions(repo_index, changed_lines)


# ============================================================
# DISPLAY ISSUES
# ============================================================

def print_issue(issue, severity):
    title = f"[{issue['rule_id']}] {issue['title']}"
    color = RED if severity == "ERROR" else YELLOW
    print(f"{color}{title}{RESET}")
    print(f"File    : {issue['file']}")
    print(f"Line    : {issue['line']}")
    print(f"Issue   : {issue['message']}")
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
    result_color = RED
elif warnings:
    result = "PASSED WITH WARNINGS"
    result_color = YELLOW
else:
    result = "PASSED"
    result_color = GREEN

print(f"Result   : {result_color}{result}{RESET}")
print("=" * 70)

if errors:
    sys.exit(1)
sys.exit(0)
