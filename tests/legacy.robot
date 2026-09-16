*** Settings ***
Library    SeleniumLibrary


*** Variables ***
${btn_legacy}    xpath=//button[@id="legacy"]


*** Test Cases ***
TC_001 - Legacy Test
    TC_001_TS_001 - Legacy Step


*** Keywords ***
TC_001_TS_001 - Legacy Step
    Log    Legacy test step
    Sleep    5s