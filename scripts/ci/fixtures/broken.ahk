#Requires AutoHotkey v2.0
; Deliberately broken fixture for the CI negative test (scripts/ci/ahk-run.ps1 -Validate -ExpectFailure).
; /validate must exit non-zero on it, which settles hypothesis H13. Do not "fix" this file.

Broken() {
    x := (1 +
    return x
}
