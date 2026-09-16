*** Settings ***
Library    SeleniumLibrary


*** Variables ***
${btn_submit}    xpath=//button[@id="submit"]
${txt_email}     xpath=//input[@id="email"]


*** Test Cases ***
TC_001 - Proceed to ePayments
    Search for the application and click Proceed to ePayments

TC_002 - Payment Validation
    TC_001_TS_001 - Login To ZAU Evaluator


*** Keywords ***
Search for the application and click Proceed to ePayments
    Log    Searching application

TC_001_TS_001 - Login To ZAU Evaluator
    Log    Login