*** Settings ***
Library    SeleniumLibrary


*** Variables ***
${submit_button}    =//button[@id="submit"]
${txt_email}        xpath=//input[@id="email"]


*** Test Cases ***
TC_001 - Proceed to ePayments
    TC_001_TS_001 - Go to ZAU Module and click View Application List
    Search for the application and click Proceed to ePayments
    TC_002_TS_003 - Select Mode of Payment

Payment Validation
    TC_002_TS_001 - Login To ZAU Evaluator And Go To Zoning Module


*** Keywords ***
TC_001_TS_001 - Go to ZAU Module and click View Application List
    Wait Until Element Is Visible    ${submit_button}    5s
    Click Element                    ${submit_button}
    Sleep                            10s

TC_002_TS_001 - Login To ZAU Evaluator And Go To Zoning Module
    Log    Login