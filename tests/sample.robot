*** Settings ***
Library    SeleniumLibrary


*** Variables ***
${submit_button}    =//button[@id="submit"]
${txt_email}        xpath=//input[@id="email"]


*** Test Cases ***
Sample Login Test
    Log    Hello from Robot Framework
    Sample Keyword


*** Keywords ***
Sample Keyword
    Sleep    10s
    Log    This keyword exists