*** Settings ***
Library    SeleniumLibrary


*** Variables ***
${bad_button}    =//button[@id="legacy"]


*** Test Cases ***
TC_001 - Legacy Test
    TC_001_TS_001 - Legacy Step


*** Keywords ***
TC_001_TS_001 - Legacy Step
    Sleep    20s