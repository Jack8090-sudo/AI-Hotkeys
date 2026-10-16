; =========================================================
;  AI-Hotkeys — installer
;  Installa: script, Python portatile, AutoHotkey v2.
;  Controlla Ollama (lo installa se manca), NON scarica il modello.
; =========================================================

Unicode true
Target amd64-unicode
SetCompressor /SOLID lzma
RequestExecutionLevel user

!define APP      "AI-Hotkeys"
!define VERSION  "1.0.0"
!define MODEL    "gemma4:12b-it-qat"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP}"
OutFile "AI-Hotkeys-Setup.exe"
InstallDir "C:\AI-Hotkeys"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
BrandingText "${APP} ${VERSION}"
ShowInstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "Installer di ${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Uso personale"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "StrFunc.nsh"
${StrStr}

!define MUI_ICON   "payload\app\icon.ico"
!define MUI_UNICON "payload\app\icon.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Installazione di AI-Hotkeys"
!define MUI_WELCOMEPAGE_TEXT "AI-Hotkeys usa Gemma in locale tramite tre tasti:$\r$\n$\r$\n    PgUp  →  correggi il testo selezionato$\r$\n    PgDn  →  riassumi$\r$\n    End    →  spiega$\r$\n$\r$\nVerranno installati il programma, Python e AutoHotkey (versioni portatili, solo per AI-Hotkeys). Se manca, verrà installato anche Ollama.$\r$\n$\r$\nIl modello ${MODEL} NON viene scaricato: se non lo hai già, alla fine ti verrà indicato il comando."

!define MUI_FINISHPAGE_TITLE "AI-Hotkeys è installato"
!define MUI_FINISHPAGE_TEXT "Seleziona del testo e premi PgUp, PgDn o End.$\r$\n$\r$\nSe non hai ancora il modello, apri il Prompt dei comandi ed esegui:$\r$\n    ollama pull ${MODEL}$\r$\n$\r$\nConfigurazione e prompt: tasto destro sull'icona ✦ nella barra delle applicazioni."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Avvia AI-Hotkeys ora"
!define MUI_FINISHPAGE_RUN_FUNCTION StartApp

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Italian"


; ---------------------------------------------------------
; Chiude le istanze in esecuzione (per poter sovrascrivere)
; ---------------------------------------------------------
!macro StopRunning
    InitPluginsDir
    File "/oname=$PLUGINSDIR\stop.ps1" "stop.ps1"
    DetailPrint "Chiusura di AI-Hotkeys se è in esecuzione…"
    nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\stop.ps1" -Dir "$INSTDIR"'
    Pop $0
!macroend


; =========================================================
; SEZIONI
; =========================================================

Section "AI-Hotkeys (obbligatorio)" SecMain
    SectionIn RO

    !insertmacro StopRunning

    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "payload\app\*.*"

    ; config.ini: non sovrascrivere la configurazione esistente
    SetOverwrite off
    File "payload\config.ini"
    SetOverwrite on

    SetOutPath "$INSTDIR\python"
    File /r "payload\python\*.*"

    SetOutPath "$INSTDIR\ahk"
    File /r "payload\ahk\*.*"

    CreateDirectory "$INSTDIR\work"

    ; Menu Start
    CreateDirectory "$SMPROGRAMS\${APP}"
    CreateShortCut "$SMPROGRAMS\${APP}\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
    CreateShortCut "$SMPROGRAMS\${APP}\Configurazione.lnk" "notepad.exe" '"$INSTDIR\config.ini"'
    CreateShortCut "$SMPROGRAMS\${APP}\Modifica i prompt.lnk" "notepad.exe" '"$INSTDIR\prompts.py"'
    CreateShortCut "$SMPROGRAMS\${APP}\Disinstalla.lnk" "$INSTDIR\Uninstall.exe"

    ; Disinstallazione
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


Section "Avvia con Windows" SecStartup
    CreateShortCut "$SMSTARTUP\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
SectionEnd


Section /o "Collegamento sul Desktop" SecDesktop
    CreateShortCut "$DESKTOP\AI-Hotkeys.lnk" "$INSTDIR\ahk\AutoHotkey64.exe" '"$INSTDIR\main.ahk"' "$INSTDIR\icon.ico"
SectionEnd


Section "Controlla Ollama (installalo se manca)" SecOllama
    Call FindOllama
    Pop $1

    ${If} $1 == ""
        MessageBox MB_YESNO|MB_ICONQUESTION "Ollama non è installato.$\r$\n$\r$\nVuoi installarlo adesso con winget? (download di circa 1 GB)$\r$\n$\r$\nScegli No per aprire la pagina di download." /SD IDNO IDNO ollama_page

        DetailPrint "Installazione di Ollama con winget (può richiedere qualche minuto)…"
        nsExec::ExecToLog 'winget install --id Ollama.Ollama -e --silent --accept-source-agreements --accept-package-agreements'
        Pop $0

        Call FindOllama
        Pop $1
        ${If} $1 != ""
            DetailPrint "Ollama installato."
            Goto check_model
        ${EndIf}

        MessageBox MB_OK|MB_ICONEXCLAMATION "Non sono riuscito a installare Ollama automaticamente.$\r$\nSi aprirà la pagina di download: installalo e poi esegui  ollama pull ${MODEL}" /SD IDOK

        ollama_page:
        ExecShell "open" "https://ollama.com/download"
        Goto done
    ${EndIf}

    check_model:
    DetailPrint "Ollama trovato: $1"
    nsExec::ExecToStack '"$1" list'
    Pop $0
    Pop $2
    ${StrStr} $3 $2 "${MODEL}"
    ${If} $3 == ""
        DetailPrint "Il modello ${MODEL} non è ancora scaricato."
        MessageBox MB_OK|MB_ICONINFORMATION "Ollama è installato, ma il modello ${MODEL} non è stato trovato.$\r$\n$\r$\nPer scaricarlo apri il Prompt dei comandi ed esegui:$\r$\n$\r$\n    ollama pull ${MODEL}$\r$\n$\r$\n(Se Ollama non era avviato, il modello potrebbe esserci comunque.)" /SD IDOK
    ${Else}
        DetailPrint "Modello ${MODEL} trovato."
    ${EndIf}

    done:
SectionEnd


LangString DESC_Main    ${LANG_ITALIAN} "Script, prompt, pagina dei risultati, Python e AutoHotkey portatili."
LangString DESC_Startup ${LANG_ITALIAN} "Attiva i tasti PgUp / PgDn / End automaticamente all'accensione del PC."
LangString DESC_Desktop ${LANG_ITALIAN} "Icona sul Desktop per avviare AI-Hotkeys."
LangString DESC_Ollama  ${LANG_ITALIAN} "Verifica che Ollama sia installato e che il modello ${MODEL} sia presente (il modello non viene scaricato)."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_Main)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} $(DESC_Startup)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_Desktop)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecOllama}  $(DESC_Ollama)
!insertmacro MUI_FUNCTION_DESCRIPTION_END


; =========================================================
; FUNZIONI
; =========================================================

; Restituisce sullo stack il percorso di ollama.exe, oppure ""
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
        ; prima riga dell'output
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
; DISINSTALLAZIONE
; =========================================================

Section "Uninstall"
    !insertmacro StopRunning

    Delete "$SMSTARTUP\AI-Hotkeys.lnk"
    Delete "$DESKTOP\AI-Hotkeys.lnk"
    RMDir /r "$SMPROGRAMS\${APP}"

    ; Solo i file installati: backup e file tuoi restano
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

    MessageBox MB_YESNO|MB_ICONQUESTION "Vuoi eliminare anche la configurazione (config.ini) e i file temporanei (cartella work)?" /SD IDNO IDNO keep_data
        Delete "$INSTDIR\config.ini"
        RMDir /r "$INSTDIR\work"
    keep_data:

    RMDir "$INSTDIR"

    DeleteRegKey HKCU "${UNINSTKEY}"
    DeleteRegKey HKCU "Software\${APP}"
SectionEnd
