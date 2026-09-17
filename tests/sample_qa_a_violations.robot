*** Settings ***
Resource    sample_qa_a_resources.resource

*** Variables ***
${btn_submit}          xpath=//button[@id="submit"]
${submit_button}       xpath=//button[@id="submit"]
${QA_URL}              https://example-qa.test/

*** Test Cases ***
TC_001 - Sample QA-A Violations
    TC_001_TS_001 - Open Application
    TC_001_TS_002 - Prepare Data
    TC_001_TS_002 - Submit Application

*** Keywords ***
TC_001_TS_001 - Open Application
    Go To    https://example-qa.test/

TC_001_TS_002 - Prepare Data
    ${used_value}=    Set Variable    hello
    ${unused_value}=    Set Variable    goodbye
    Log    ${used_value}
    Shared Used Keyword

TC_001_TS_003 - Submit Application
    Click Element    ${btn_submit}

Unused Local Keyword
    Log    This keyword is never called

Duplicate Action A
    Wait Until Element Is Visible    ${btn_submit}    5s
    Click Element    ${btn_submit}

Duplicate Action B
    Wait Until Element Is Visible    ${btn_submit}    5s
    Click Element    ${btn_submit}
