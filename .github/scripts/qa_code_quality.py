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


# ============================================================
# ERROR HANDLING
# ============================================================

def add_error(file, line_number, rule_id, title, message):
    """
    Store a QA-A code quality violation.
    """

    errors.append({
        "file": str(file),
        "line": line_number,
        "rule_id": rule_id,
        "title": title,
        "message": message,
    })


# ============================================================
# FILE CHECKS
# ============================================================

def check_file(file):
    """
    Run QA-A code quality checks against a Robot Framework
    .robot or .resource file.
    """

    content = file.read_text(encoding="utf-8")

    for line_number, line in enumerate(content.splitlines(), start=1):

        # Ignore comments
        stripped_line = line.strip()

        if not stripped_line or stripped_line.startswith("#"):
            continue

        # ----------------------------------------------------
        # QA-A001 — LOCATOR NAMING VIOLATION
        #
        # Locator variables must use an approved prefix.
        #
        # Good:
        # ${btn_submit}
        # ${txt_email}
        # ${ddl_application_type}
        #
        # Bad:
        # ${submit_button}
        # ${email_field}
        # ----------------------------------------------------

        variable_match = re.search(r"\$\{([^}]+)\}", line)

        if variable_match:
            variable_name = variable_match.group(1)

            # Determine whether the line appears to contain
            # a locator value.
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

        # ----------------------------------------------------
        # QA-A002 — INVALID XPATH FORMAT
        #
        # XPath locators must explicitly use:
        #
        # xpath=//
        #
        # Good:
        # ${btn_submit}    xpath=//button[@id="submit"]
        #
        # Bad:
        # ${btn_submit}    =//button[@id="submit"]
        # ----------------------------------------------------

        if "=//" in line and "xpath=//" not in line.lower():
            add_error(
                file,
                line_number,
                "QA-A002",
                "Invalid XPath Format",
                (
                    "XPath locator must explicitly use 'xpath=//'."
                ),
            )

        # ----------------------------------------------------
        # QA-A003 — SLEEP DURATION VIOLATION
        #
        # Sleep is allowed up to 5 seconds.
        #
        # Good:
        # Sleep    2s
        # Sleep    5s
        #
        # Bad:
        # Sleep    6s
        # Sleep    10s
        # ----------------------------------------------------

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
# RESULTS
# ============================================================

if errors:

    print("=" * 70)
    print("QA-A CODE QUALITY ISSUES")
    print("=" * 70)
    print()

    for error in errors:

        full_title = (
            f"{error['rule_id']} - {error['title']}"
        )

        # GitHub Actions annotation.
        #
        # This allows GitHub to associate the error with
        # the exact file and line where the violation occurred.
        print(
            f"::error "
            f"file={error['file']},"
            f"line={error['line']},"
            f"title={full_title}::"
            f"{full_title}: {error['message']}"
        )

        # Human-readable console output.
        print(f"   Rule: {full_title}")
        print(f"   File: {error['file']}")
        print(f"   Line: {error['line']}")
        print(f"   Issue: {error['message']}")
        print()

    print("=" * 70)

    issue_word = "issue" if len(errors) == 1 else "issues"

    print(
        f"QA-A Code Quality FAILED - "
        f"{len(errors)} {issue_word} found."
    )

    print("=" * 70)

    sys.exit(1)


# ============================================================
# SUCCESS
# ============================================================

print("=" * 70)
print("QA-A Code Quality PASSED")
print("No QA-A code quality violations found.")
print("=" * 70)

sys.exit(0)