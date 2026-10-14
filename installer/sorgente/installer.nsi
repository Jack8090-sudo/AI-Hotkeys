; =========================================================
;  AI-Hotkeys — installer
;  Installs: script, portable Python, AutoHotkey v2.
;  Checks Ollama (installs it if missing), does NOT download the model.
; =========================================================

Unicode true
Target amd64-unicode
SetCompressor /SOLID lzma
RequestExecutionLevel user

!define APP      "AI-Hotkeys"
!define VERSION  "1.0.0"
!define MODEL    "qwen3.5:9b"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP}"
OutFile "AI-Hotkeys-Setup.exe"
InstallDir "C:\AI-Hotkeys"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
BrandingText "${APP} ${VERSION}"
ShowInstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "Installer of ${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Personal use"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "StrFunc.nsh"
${StrStr}

!define MUI_ICON   "payload\app\icon.ico"
!define MUI_UNICON "payload\app\icon.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Installing AI-Hotkeys"
!define MUI_WELCOMEPAGE_TEXT "AI-Hotkeys uses local Qwen with three keys:$\r$\n$\r$\n    PgUp  →  fix the selected text$\r$\n    PgDn  →  summarize$\r$\n    End    →  explain$\r$\n$\r$\nThe program, Python and AutoHotkey will be installed (portable versions, only for AI-Hotkeys). If missing, Ollama will be installed too.$\r$\n$\r$\nThe ${MODEL} model is NOT downloaded: if you do not have it yet, you will be given the command at the end."

!define MUI_FINISHPAGE_TITLE "AI-Hotkeys is installed"
!define MUI_FINISHPAGE_TEXT "Select some text and press PgUp, PgDn or End.$\r$\n$\r$\nIf you do not have the model yet, open the Command Prompt and run:$\r$\n    ollama pull ${MODEL}$\r$\n$\r$\nConfiguration and prompts: right-click the ✦ icon in the taskbar."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch AI-Hotkeys now"
!define MUI_FINISHPAGE_RUN_FUNCTION StartApp

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"


; ---------------------------------------------------------
; Closes the running instances (so files can be overwritten)
; ---------------------------------------------------------
!macro StopRunning
    InitPluginsDir
    File "/oname=$PLUGINSDIR\stop.ps1" "stop.ps1"
    DetailPrint "Closing AI-Hotkeys if it is running…"
    nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\stop.ps1" -Dir "$INSTDIR"'
    Pop $0
!macroend


; =========================================================
; SECTIONS
; =========================================================

Section "AI-Hotkeys (required)" SecMain
    SectionIn RO

    !insertmacro StopRunning

    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "payload\app\*.*"

    ; config.ini: do not overwrite the existing configuration
    SetOverwrite off
    File "payload\config.ini"
    SetOverwrite on

    SetOutPath "$INSTDIR\python"
    File /r "payload\python\*.*"

    SetOutPath "$INSTDIR\ahk"
    File /r "payload\ahk\*.*"

    CreateDirectory "$INSTDIR\work"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\${APP}"
    CreateShortCut "$SMPROGRAMS\${APP}\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
    CreateShortCut "$SMPROGRAMS\${APP}\Configuration.lnk" "notepad.exe" '"$INSTDIR\config.ini"'
    CreateShortCut "$SMPROGRAMS\${APP}\Edit prompts.lnk" "notepad.exe" '"$INSTDIR\prompts.py"'
    CreateShortCut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Uninstallation
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "Software\${APP}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APP}"
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${APP}"
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\icon.ico"
    WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
SectionEnd


Section "Start with Windows" SecStartup
    CreateShortCut "$SMSTARTUP\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
SectionEnd


Section /o "Desktop shortcut" SecDesktop
    CreateShortCut "$DESKTOP\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
SectionEnd


Section "Check Ollama (install if missing)" SecOllama
    Call FindOllama
    Pop $1

    ${If} $1 == ""
        MessageBox MB_YESNO|MB_ICONQUESTION "Ollama is not installed.$\r$\n$\r$\nDo you want to install it now with winget? (about 1 GB download)$\r$\n$\r$\nChoose No to open the download page." /SD IDNO IDNO ollama_page

        DetailPrint "Installing Ollama with winget (may take a few minutes)…"
        nsExec::ExecToLog 'winget install --id Ollama.Ollama -e --silent --accept-source-agreements --accept-package-agreements'
        Pop $0

        Call FindOllama
        Pop $1
        ${If} $1 != ""
            DetailPrint "Ollama installed."
            Goto check_model
        ${EndIf}

        MessageBox MB_OK|MB_ICONEXCLAMATION "Could not install Ollama automatically.$\r$\nThe download page will open: install it and then run  ollama pull ${MODEL}" /SD IDOK

        ollama_page:
        ExecShell "open" "https://ollama.com/download"
        Goto done
    ${EndIf}

    check_model:
    DetailPrint "Ollama found: $1"
    nsExec::ExecToStack '"$1" list'
    Pop $0
    Pop $2
    ${StrStr} $3 $2 "${MODEL}"
    ${If} $3 == ""
        DetailPrint "The ${MODEL} model is not downloaded yet."
        MessageBox MB_OK|MB_ICONINFORMATION "Ollama is installed, but the ${MODEL} model was not found.$\r$\n$\r$\nTo download it open the Command Prompt and run:$\r$\n$\r$\n    ollama pull ${MODEL}$\r$\n$\r$\n(If Ollama was not running, the model may be there anyway.)" /SD IDOK
    ${Else}
        DetailPrint "${MODEL} model found."
    ${EndIf}

    done:
SectionEnd


LangString DESC_Main    ${LANG_ENGLISH} "Script, prompts, results page, portable Python and AutoHotkey."
LangString DESC_Startup ${LANG_ENGLISH} "Enables the PgUp / PgDn / End keys automatically when the PC starts."
LangString DESC_Desktop ${LANG_ENGLISH} "Desktop icon to launch AI-Hotkeys."
LangString DESC_Ollama  ${LANG_ENGLISH} "Checks that Ollama is installed and that the ${MODEL} model is present (the model is not downloaded)."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_Main)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} $(DESC_Startup)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_Desktop)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecOllama}  $(DESC_Ollama)
!insertmacro MUI_FUNCTION_DESCRIPTION_END


; =========================================================
; FUNCTIONS
; =========================================================

; Returns the ollama.exe path on the stack, or ""
Function FindOllama
    ${If} ${FileExists} "$LOCALAPPDATA\Programs\Ollama\ollama.exe"
        Push "$LOCALAPPDATA\Programs\Ollama\ollama.exe"
        Return
    ${EndIf}
    ${If} ${FileExists} "$PROGRAMFILES64\Ollama\ollama.exe"
        Push "$PROGRAMFILES64\Ollama\ollama.exe"
        Return
    ${EndIf}
    nsExec::ExecToStack 'cmd.exe /c where ollama'
    Pop $0
    Pop $R0
    ${If} $0 == 0
        ; first line of the output
        StrCpy $R1 0
        loop:
            StrCpy $R2 $R0 1 $R1
            ${If} $R2 == "$\r"
            ${OrIf} $R2 == "$\n"
            ${OrIf} $R2 == ""
                StrCpy $R0 $R0 $R1
                Push $R0
                Return
            ${EndIf}
            IntOp $R1 $R1 + 1
            Goto loop
    ${EndIf}
    Push ""
FunctionEnd

Function StartApp
    Exec '"$INSTDIR\ahk\AutoHotkey64.exe" "$INSTDIR\main.ahk"'
FunctionEnd


; =========================================================
; UNINSTALLATION
; =========================================================

Section "Uninstall"
    !insertmacro StopRunning

    Delete "$SMSTARTUP\AI-Hotkeys.lnk"
    Delete "$DESKTOP\AI-Hotkeys.lnk"
    RMDir /r "$SMPROGRAMS\${APP}"

    ; Only installed files: backups and your files are kept
    RMDir /r "$INSTDIR\python"
    RMDir /r "$INSTDIR\ahk"
    RMDir /r "$INSTDIR\static"
    RMDir /r "$INSTDIR\__pycache__"
    RMDir /r "$INSTDIR\actions\__pycache__"
    Delete "$INSTDIR\actions\rewrite.py"
    Delete "$INSTDIR\actions\summarize.py"
    Delete "$INSTDIR\actions\explain.py"
    Delete "$INSTDIR\actions\obsidian_todo.py"
    Delete "$INSTDIR\actions\unload.py"
    RMDir  "$INSTDIR\actions"
    Delete "$INSTDIR\main.ahk"
    Delete "$INSTDIR\viewer.py"
    Delete "$INSTDIR\qwen_client.py"
    Delete "$INSTDIR\prompts.py"
    Delete "$INSTDIR\websearch.py"
    Delete "$INSTDIR\settings.py"
    Delete "$INSTDIR\pages.py"
    Delete "$INSTDIR\config_edit.py"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\Uninstall.exe"

    MessageBox MB_YESNO|MB_ICONQUESTION "Do you also want to delete the configuration (config.ini) and temporary files (work folder)?" /SD IDNO IDNO keep_data
        Delete "$INSTDIR\config.ini"
        RMDir /r "$INSTDIR\work"
    keep_data:

    RMDir "$INSTDIR"

    DeleteRegKey HKCU "${UNINSTKEY}"
    DeleteRegKey HKCU "Software\${APP}"
SectionEnd
