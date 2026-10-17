; =========================================================
;  AI-Hotkeys — installer
;  Installs: script, portable Python, AutoHotkey v2.
;  Checks Ollama (installs it if missing), does NOT download the model.
;
;  Built by build\build.ps1, which stages this file next to payload\, manifest.txt and the
;  generated uninstall.nsh, and runs:  makensis /INPUTCHARSET UTF8 /DVERSION=<VERSION> installer.nsi
; =========================================================

Unicode true
; The official NSIS distribution only ships x86 stubs. A 32-bit installer installs the x64
; payload fine: HKCU is not redirected and stop.ps1 uses CIM, which works across bitness.
Target x86-unicode
ManifestDPIAware true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!ifndef VERSION
    !error "VERSION is not defined: build with build\build.ps1, or pass /DVERSION=x.y.z to makensis"
!endif

!define APP       "AI-Hotkeys"
!define MODEL     "qwen3.5:9b"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"
!define APPKEY    "Software\${APP}"
; v1.0.0 installed here by default (D1/D11: offer to migrate away from it)
!define LEGACY_DIR "C:\AI-Hotkeys"
; Full paths only: CreateProcess would otherwise search the installer's own folder first.
!define POWERSHELL '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File'

Name "${APP}"
OutFile "AI-Hotkeys-Setup.exe"
; D1: per-user folder whose ACL (inherited from the profile) grants only the user, SYSTEM and Administrators.
InstallDir "$LOCALAPPDATA\Programs\${APP}"
BrandingText "${APP} ${VERSION}"
ShowInstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "Installer of ${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Personal use"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "StrFunc.nsh"
${StrStr}

Var OldDir       ; InstallDir of the previous installation (registry), normalized
Var OldVer       ; its DisplayVersion
Var ChkDir       ; .onVerifyInstDir writability cache: last folder tested...
Var ChkOk        ; ...and its result (1 = writable)

!define MUI_ICON   "payload\app\icon.ico"
!define MUI_UNICON "payload\app\icon.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Installing AI-Hotkeys"
!define MUI_WELCOMEPAGE_TEXT "AI-Hotkeys uses local Qwen with three keys:$\r$\n$\r$\n    PgUp  →  fix the selected text$\r$\n    PgDn  →  summarize$\r$\n    End    →  explain$\r$\n$\r$\nThe program, Python and AutoHotkey will be installed (portable versions, only for AI-Hotkeys). If missing, Ollama will be installed too.$\r$\n$\r$\nThe ${MODEL} model is NOT downloaded: if you do not have it yet, you will be given the command at the end."

!define MUI_DIRECTORYPAGE_TEXT_TOP "The default folder is private to your Windows account.$\r$\nThe folder must be writable, must not be the root of a drive and must not be inside a git repository. A folder outside your user profile is restricted to your account, SYSTEM and Administrators."

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
; Helpers shared by the installer and the uninstaller
; ---------------------------------------------------------

; Removes trailing \ or / from the string on top of the stack (a trailing backslash before
; a closing quote would break the quoting of command-line arguments).
!macro AIH_NORM_DIR_FN prefix
Function ${prefix}AihNormDir
    Exch $0
    Push $1
    again:
        StrCpy $1 $0 1 -1
        ${If} $1 == "\"
        ${OrIf} $1 == "/"
            StrCpy $0 $0 -1
            Goto again
        ${EndIf}
    Pop $1
    Exch $0
FunctionEnd
!macroend
!insertmacro AIH_NORM_DIR_FN ""

; Closes the instances running from a folder (so files can be overwritten).
; Leaves stop.ps1's exit code in $0.
!macro StopRunning DIR
    InitPluginsDir
    File "/oname=$PLUGINSDIR\stop.ps1" "stop.ps1"
    DetailPrint "Closing AI-Hotkeys if it is running from ${DIR}…"
    nsExec::ExecToLog '${POWERSHELL} "$PLUGINSDIR\stop.ps1" -Dir "${DIR}"'
    Pop $0
!macroend


; ---------------------------------------------------------
; Install-folder rules (C09 / D1)
; ---------------------------------------------------------

; In: folder on the stack. Out: "" if it can be used, otherwise the reason, on the stack.
; Rejects: relative paths, drive roots, folders inside a git repository (.git in the folder or
; in any parent: the v1.0.0 default C:\AI-Hotkeys is also the source repository), and folders
; that cannot be written. Called on every keystroke by .onVerifyInstDir, so the write test is
; cached per tested folder.
Function AihCheckDir
    Exch $0
    Push $1
    Push $2
    Push $3

    Push $0
    Call AihNormDir
    Pop $0
    StrCpy $3 ""

    ; absolute: "X:\..." or "\\server\share\..."
    StrCpy $1 $0 1 1
    StrCpy $2 $0 2
    ${If} $1 != ":"
    ${AndIf} $2 != "\\"
        StrCpy $3 "The folder must be a full path, such as $LOCALAPPDATA\Programs\${APP}."
        Goto done
    ${EndIf}

    ${GetRoot} $0 $1
    ${If} $0 == $1
        StrCpy $3 "The root of a drive cannot be used: choose a folder."
        Goto done
    ${EndIf}

    StrCpy $1 $0
    gitloop:
        ${If} ${FileExists} "$1\.git"
            StrCpy $3 "$1 is a git repository (it contains .git): choose another folder."
            Goto done
        ${EndIf}
        ${GetParent} $1 $2
        ${If} $2 == ""
        ${OrIf} $2 == $1
            Goto gitdone
        ${EndIf}
        StrCpy $1 $2
        Goto gitloop
    gitdone:

    ; nearest folder that already exists
    StrCpy $1 $0
    existloop:
        ${IfNot} ${FileExists} "$1\*.*"
            ${GetParent} $1 $2
            ${If} $2 == ""
            ${OrIf} $2 == $1
                StrCpy $3 "The drive of this folder does not exist."
                Goto done
            ${EndIf}
            StrCpy $1 $2
            Goto existloop
        ${EndIf}

    ${If} $1 != $ChkDir
        StrCpy $ChkDir $1
        StrCpy $ChkOk 0
        ClearErrors
        ${If} $1 == $0
            ; the folder exists: can we create files in it?
            FileOpen $2 "$1\aih-write-test.tmp" w
            ${IfNot} ${Errors}
                FileClose $2
                Delete "$1\aih-write-test.tmp"
                StrCpy $ChkOk 1
            ${EndIf}
        ${Else}
            ; it does not exist yet: can we create a folder where it will be?
            CreateDirectory "$1\aih-write-test.tmp"
            ${IfNot} ${Errors}
                RMDir "$1\aih-write-test.tmp"
                StrCpy $ChkOk 1
            ${EndIf}
        ${EndIf}
    ${EndIf}
    ${If} $ChkOk != 1
        StrCpy $3 "$1 is not writable with your account: choose another folder."
    ${EndIf}

    done:
    StrCpy $0 $3
    Pop $3
    Pop $2
    Pop $1
    Exch $0
FunctionEnd

Function .onVerifyInstDir
    Push $0
    Push $INSTDIR
    Call AihCheckDir
    Pop $0
    ${If} $0 != ""
        Pop $0
        Abort
    ${EndIf}
    Pop $0
FunctionEnd

; In: base folder, then (top) folder. Out: 1 if folder is base or inside it, else 0.
Function AihIsUnder
    Exch $0      ; folder
    Exch
    Exch $1      ; base
    Push $2
    Push $3
    StrCpy $2 "0"
    ${If} $1 != ""
        ${If} $0 == $1
            StrCpy $2 "1"
        ${Else}
            StrLen $3 "$1\"
            StrCpy $3 $0 $3
            ${If} $3 == "$1\"          ; StrCmp is case-insensitive
                StrCpy $2 "1"
            ${EndIf}
        ${EndIf}
    ${EndIf}
    StrCpy $0 $2
    Pop $3
    Pop $2
    Pop $1
    Exch $0
FunctionEnd

; A folder outside the user profile inherits the parent's ACL (for example C:\ grants
; Authenticated Users the right to create and modify). Everything in it runs as the user at
; login, so it gets an explicit, non-inherited ACL: the user, SYSTEM and Administrators only.
Function AihSecureDir
    Push $LOCALAPPDATA
    Push $INSTDIR
    Call AihIsUnder
    Pop $0
    ${If} $0 == 1
        Return
    ${EndIf}
    Push $PROFILE
    Push $INSTDIR
    Call AihIsUnder
    Pop $0
    ${If} $0 == 1
        Return
    ${EndIf}

    DetailPrint "Restricting $INSTDIR to your account, SYSTEM and Administrators…"
    ; current user's SID: whoami prints  "DOMAIN\user","S-1-5-21-…"
    nsExec::ExecToStack '"$SYSDIR\whoami.exe" /user /fo csv /nh'
    Pop $0
    Pop $1
    ${StrStr} $2 $1 '"S-1-'
    StrCpy $2 $2 "" 1
    StrCpy $3 0
    sidloop:
        StrCpy $4 $2 1 $3
        ${If} $4 != '"'
        ${AndIf} $4 != ""
            IntOp $3 $3 + 1
            Goto sidloop
        ${EndIf}
    StrCpy $2 $2 $3
    StrCpy $4 $2 4
    ${If} $0 != 0
    ${OrIf} $4 != "S-1-"
        MessageBox MB_OK|MB_ICONSTOP "Could not determine your Windows account (whoami: $0), so the permissions of$\r$\n$INSTDIR$\r$\ncannot be restricted. Installation stopped: choose a folder inside your user profile." /SD IDOK
        SetErrorLevel 2
        Abort
    ${EndIf}

    ; S-1-5-18 = SYSTEM, S-1-5-32-544 = Administrators. /inheritance:r drops the inherited ACEs.
    nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$INSTDIR" /inheritance:r /grant:r "*$2:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /C /Q'
    Pop $0
    ${If} $0 == 0
        ; explicit grants for Everyone, Authenticated Users and Users, on the folder and anything
        ; already in it (an existing custom folder)
        nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$INSTDIR" /remove:g "*S-1-1-0" "*S-1-5-11" "*S-1-5-32-545" /T /C /Q'
        Pop $0
    ${EndIf}
    ${If} $0 != 0
        MessageBox MB_OK|MB_ICONSTOP "Could not restrict the permissions of$\r$\n$INSTDIR$\r$\n(icacls: $0). Installation stopped: choose a folder inside your user profile." /SD IDOK
        SetErrorLevel 2
        Abort
    ${EndIf}
FunctionEnd


; ---------------------------------------------------------
; Previous installations (D11)
; ---------------------------------------------------------

Function .onInit
    ReadRegStr $OldDir HKCU "${APPKEY}" "InstallDir"
    ReadRegStr $OldVer HKCU "${UNINSTKEY}" "DisplayVersion"
    Push $OldDir
    Call AihNormDir
    Pop $OldDir

    ; A later install in a custom folder is upgraded in place, by default. The v1.0.0 default
    ; C:\AI-Hotkeys, or a folder that no longer passes the rules, gets the new default folder
    ; instead and the migration is offered. /D=<folder> always wins.
    ${If} $OldDir != ""
    ${AndIf} $INSTDIR == "$LOCALAPPDATA\Programs\${APP}"
    ${AndIf} $OldDir != "${LEGACY_DIR}"
        Push $OldDir
        Call AihCheckDir
        Pop $0
        ${If} $0 == ""
            StrCpy $INSTDIR $OldDir
        ${EndIf}
    ${EndIf}
FunctionEnd

; Copies config.ini from the old folder, unless the new folder already has one (I13).
Function AihCopyOldConfig
    ${If} ${FileExists} "$OldDir\config.ini"
    ${AndIfNot} ${FileExists} "$INSTDIR\config.ini"
        ClearErrors
        CopyFiles /SILENT "$OldDir\config.ini" "$INSTDIR\config.ini"
        ${If} ${Errors}
            DetailPrint "Could not copy $OldDir\config.ini: the default configuration will be used."
        ${Else}
            DetailPrint "Copied your configuration from $OldDir\config.ini"
        ${EndIf}
    ${EndIf}
FunctionEnd

; The registry points to an installation in another folder. With consent: stop it, copy its
; config.ini, disable its uninstaller (it would delete this installation's registry keys and
; shortcuts) and remove its shortcuts. Its folder is never deleted. Silent mode: config only.
Function AihMigrate
    ${If} ${Silent}
        Call AihCopyOldConfig
        DetailPrint "Silent install: only config.ini was taken from $OldDir; that installation was not changed."
        Return
    ${EndIf}

    MessageBox MB_YESNO|MB_ICONQUESTION "An existing AI-Hotkeys installation was found in:$\r$\n    $OldDir$\r$\n$\r$\nMove it to the new folder? This will:$\r$\n  • close the old copy if it is running$\r$\n  • copy its config.ini (your settings)$\r$\n  • disable its uninstaller (renamed to Uninstall.exe.disabled-by-${VERSION})$\r$\n  • remove its Start menu, Startup and Desktop shortcuts$\r$\n$\r$\nThe old folder itself is NOT deleted.$\r$\n$\r$\nChoose No to install without touching the old copy." IDYES migrate
    DetailPrint "Migration declined: $OldDir was left unchanged."
    Return

    migrate:
    !insertmacro StopRunning "$OldDir"
    ${If} $0 != 0
        DetailPrint "Warning: some processes of the old installation could not be closed ($0)."
    ${EndIf}

    Call AihCopyOldConfig

    ${If} ${FileExists} "$OldDir\Uninstall.exe"
        Delete "$OldDir\Uninstall.exe.disabled-by-${VERSION}"
        ClearErrors
        Rename "$OldDir\Uninstall.exe" "$OldDir\Uninstall.exe.disabled-by-${VERSION}"
        ${If} ${Errors}
            MessageBox MB_OK|MB_ICONEXCLAMATION "Could not rename$\r$\n$OldDir\Uninstall.exe$\r$\nDo not run it: it would remove the shortcuts and registry entries of the new installation." /SD IDOK
        ${Else}
            DetailPrint "Old uninstaller disabled: $OldDir\Uninstall.exe.disabled-by-${VERSION}"
        ${EndIf}
    ${EndIf}

    ; v1.0.0 shortcut names (Italian included) are listed in the legacy manifest; only the ones
    ; that point into the old folder are removed. Later versions use the same file names.
    nsExec::ExecToLog '${POWERSHELL} "$PLUGINSDIR\manifest.ps1" -Action Shortcuts -Dir "$OldDir" -Old "$PLUGINSDIR\legacy-1.0.0.manifest"'
    Pop $0

    ${If} ${FileExists} "$OldDir\.git"
        MessageBox MB_OK|MB_ICONINFORMATION "Migration done. The old folder$\r$\n    $OldDir$\r$\nwas left in place. It contains a git repository (.git), so delete it only if you no longer need that repository." /SD IDOK
    ${Else}
        MessageBox MB_OK|MB_ICONINFORMATION "Migration done. The old folder$\r$\n    $OldDir$\r$\nwas left in place: once AI-Hotkeys works from the new folder, you can delete it." /SD IDOK
    ${EndIf}
FunctionEnd


; =========================================================
; SECTIONS
; =========================================================

Section "AI-Hotkeys (required)" SecMain
    SectionIn RO

    ; .onVerifyInstDir does not run for silent installs with /D=
    Push $INSTDIR
    Call AihNormDir
    Pop $INSTDIR
    Push $INSTDIR
    Call AihCheckDir
    Pop $0
    ${If} $0 != ""
        MessageBox MB_OK|MB_ICONSTOP "Cannot install to$\r$\n$INSTDIR$\r$\n$\r$\n$0" /SD IDOK
        SetErrorLevel 2
        Abort
    ${EndIf}

    InitPluginsDir
    File "/oname=$PLUGINSDIR\manifest.ps1" "manifest.ps1"
    File "/oname=$PLUGINSDIR\legacy-1.0.0.manifest" "legacy-1.0.0.manifest"
    File "/oname=$PLUGINSDIR\new.manifest" "manifest.txt"

    CreateDirectory "$INSTDIR"
    Call AihSecureDir

    ${If} $OldDir != ""
    ${AndIf} $OldDir != $INSTDIR
    ${AndIf} ${FileExists} "$OldDir\main.ahk"
        Call AihMigrate
    ${EndIf}

    !insertmacro StopRunning "$INSTDIR"

    ; In-place upgrade of v1.0.0 (no manifest of its own): remove the files it shipped that this
    ; version no longer has (config.esempio.ini, the old python\ layout, …) and its Italian shortcuts.
    StrCpy $1 0
    ${If} ${FileExists} "$INSTDIR\config.esempio.ini"
        StrCpy $1 1
    ${EndIf}
    ${If} $OldDir == $INSTDIR
    ${AndIf} $OldVer == "1.0.0"
        StrCpy $1 1
    ${EndIf}
    ${If} ${FileExists} "$INSTDIR\main.ahk"
        ${If} $1 == 1
            DetailPrint "Upgrading AI-Hotkeys 1.0.0: removing obsolete files…"
            nsExec::ExecToLog '${POWERSHELL} "$PLUGINSDIR\manifest.ps1" -Action Upgrade -Dir "$INSTDIR" -Old "$PLUGINSDIR\legacy-1.0.0.manifest" -New "$PLUGINSDIR\new.manifest" -OldVersion 1.0.0'
            Pop $0
            nsExec::ExecToLog '${POWERSHELL} "$PLUGINSDIR\manifest.ps1" -Action Shortcuts -Dir "$INSTDIR" -Old "$PLUGINSDIR\legacy-1.0.0.manifest"'
            Pop $0
        ${EndIf}
    ${EndIf}

    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "payload\app\*.*"

    ; config.ini: do not overwrite the existing configuration (I13)
    SetOverwrite off
    File "payload\config.ini"
    SetOverwrite on

    SetOutPath "$INSTDIR\python"
    File /r "payload\python\*.*"

    SetOutPath "$INSTDIR\ahk"
    File /r "payload\ahk\*.*"

    SetOutPath "$INSTDIR"
    CreateDirectory "$INSTDIR\work"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\${APP}"
    CreateShortCut "$SMPROGRAMS\${APP}\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
    CreateShortCut "$SMPROGRAMS\${APP}\Configuration.lnk" "$WINDIR\notepad.exe" '"$INSTDIR\config.ini"'
    CreateShortCut "$SMPROGRAMS\${APP}\Edit prompts.lnk" "$WINDIR\notepad.exe" '"$INSTDIR\prompts.py"'
    CreateShortCut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Uninstallation
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${APPKEY}" "InstallDir" "$INSTDIR"
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
    !insertmacro StopRunning "$INSTDIR"

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
    DeleteRegKey HKCU "${APPKEY}"
SectionEnd
