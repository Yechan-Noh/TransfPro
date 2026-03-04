; TransfPro Windows Installer Script (NSIS)
;
; Prerequisites:
;   1. Build TransfPro.exe first: build_app.bat
;   2. Install NSIS: https://nsis.sourceforge.io/
;   3. Compile: makensis installer.nsi
;
; Output: dist\TransfPro-Setup.exe
;

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ── Application metadata ──
!define APP_NAME "TransfPro"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "TransfPro Team"
!define APP_URL "https://github.com/transfpro/transfpro"
!define APP_EXE "TransfPro.exe"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"

; ── Installer attributes ──
Name "${APP_NAME} ${APP_VERSION}"
OutFile "dist\${APP_NAME}-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin

; ── Version info (shown in file Properties) ──
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright 2024-2026 ${APP_PUBLISHER}"

; ── MUI Settings ──
!define MUI_ABORTWARNING
!define MUI_ICON "resources\transfpro_icon.ico"
!define MUI_UNICON "resources\transfpro_icon.ico"

; ── Installer pages ──
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ── Uninstaller pages ──
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ── Language ──
!insertmacro MUI_LANGUAGE "English"

; ────────────────────────────────────────────────────
; Install Section
; ────────────────────────────────────────────────────
Section "Install"
    SetOutPath "$INSTDIR"

    ; Copy all files from the PyInstaller dist folder
    File /r "dist\TransfPro\*.*"

    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Create Desktop shortcut
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Write registry keys for Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "URLInfoAbout" "${APP_URL}"

    ; Calculate and store installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "EstimatedSize" "$0"

    ; Store install directory
    WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"

SectionEnd

; ────────────────────────────────────────────────────
; Uninstall Section
; ────────────────────────────────────────────────────
Section "Uninstall"

    ; Remove files and directories
    RMDir /r "$INSTDIR"

    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    ; Remove Desktop shortcut
    Delete "$DESKTOP\${APP_NAME}.lnk"

    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    DeleteRegKey HKLM "Software\${APP_NAME}"

SectionEnd
