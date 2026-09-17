*** Variables ***
${btn_legacy}    xpath=//button[@id="legacy"]
${NotSnakeCase}    xpath=button
${snake_case}    random_button

*** Keywords ***
Search for the application and click Proceed to ePayments
    Log    Searching application
    Log    Changed files only test
    Sleep    6s

TC_001_TS_001 - Login To ZAU Evaluator
    Log    Login
    Sleep    10s
    Log     New valid change
    Sleep    10s
    Pause Execution