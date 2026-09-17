*** Variables ***
${btn_save}         xpath=//button[@id="save"]
${save_button}      xpath=//button[@id="save"]

*** Keywords ***
Shared Used Keyword
    Log    I am used by another keyword

Unused Shared Keyword
    Log    I am intentionally unused for QA-A007 testing
