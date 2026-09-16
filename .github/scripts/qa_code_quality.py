import re
import sys
from pathlib import Path


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

errors = []


def add_error(file, line_number, rule, message):
    errors.append(
        f"::error file={file},line={line_number},title={rule}::{message}"
    )


def check_file(file):
    content = file.read_text(encoding="utf-8")

    for line_number, line in enumerate(content.splitlines(), start=1):

        # ---------------------------------------------------------
        # QA-A001: Locator naming
        # ---------------------------------------------------------

        variable_match = re.search(r"\$\{([^}]+)\}", line)

        if variable_match:
            variable_name = variable_match.group(1)

            # Only treat variables containing locator-like values
            if re.search(
                r"(xpath=|id=|name=|css=|=//|(?<!xpath=)//)",
                line,
                re.IGNORECASE,
            ):
                if not variable_name.startswith(ALLOWED_LOCATOR_PREFIXES):
                    add_error(
                        file,
                        line_number,
                        "QA-A001 Locator Naming",
                        f"'${{{variable_name}}}' does not use an approved locator prefix.",
                    )

        # ---------------------------------------------------------
        # QA-A002: XPath format
        # ---------------------------------------------------------

        if "=//" in line and "xpath=//" not in line:
            add_error(
                file,
                line_number,
                "QA-A002 XPath Format",
                "XPath locator must explicitly use 'xpath=//'.",
            )

        # ---------------------------------------------------------
        # QA-A003: Sleep duration
        # ---------------------------------------------------------

        sleep_match = re.search(
            r"\bSleep\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds)?\b",
            line,
            re.IGNORECASE,
        )

        if sleep_match:
            duration = float(sleep_match.group(1))

            if duration > 5:
                add_error(
                    file,
                    line_number,
                    "QA-A003 Sleep Duration",
                    f"Sleep is {duration:g}s. Maximum allowed duration is 5 seconds. "
                    "Consider using an explicit wait.",
                )


robot_files = list(Path("").rglob("*.robot"))
robot_files += list(Path("").rglob("*.resource"))

for robot_file in robot_files:
    check_file(robot_file)


if errors:
    print("\nQA-A Code Quality Issues\n")

    for error in errors:
        print(error)

    print(f"\nFound {len(errors)} QA-A code quality issue(s).")
    sys.exit(1)


print("QA-A Code Quality checks passed.")
sys.exit(0)