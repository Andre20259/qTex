; Inno Setup script for QTeX - compiled by build.ps1 (needs Inno Setup 6: https://jrsoftware.org/isinfo.php)
; Packs dist\QTeX\ into installer\QTeX-Setup-<version>.exe
; Saved as UTF-8 with BOM so the accented publisher name displays correctly.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "QTeX"
#define MyAppExe  "QTeX.exe"

[Setup]
AppId={{6B0E4C2A-8F3D-4B8E-9C61-5A2D7E1F3B94}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=André Lopes
AppCopyright=Copyright (C) 2026 André Lopes
; License page (GPL doesn't require accepting it to use the program, but showing it is customary)
LicenseFile=LICENSE
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the user can still choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=QTeX-Setup-{#MyAppVersion}
SetupIconFile=assets\qtex.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
; Shows the GPL on a license page (with GPL you don't have to "accept" it to use the program, but showing it is customary).
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ChangesAssociations=yes

[Tasks]
Name: "desktopicon";   Description: "Create a &desktop shortcut";                         GroupDescription: "Shortcuts:"
Name: "texopenwith";   Description: "Add QTeX to ""Open with"" for .tex and .bib files";   GroupDescription: "Windows integration:"
Name: "foldercontext"; Description: "Add ""Open in QTeX"" when right-clicking a folder";   GroupDescription: "Windows integration:"

[Files]
Source: "dist\QTeX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}";       Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; ---- "Open with" for .tex / .bib
Root: HKA; Subkey: "Software\Classes\QTeX.Document";                     ValueType: string; ValueData: "LaTeX document";            Flags: uninsdeletekey; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\QTeX.Document\DefaultIcon";         ValueType: string; ValueData: "{app}\{#MyAppExe},0";        Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\QTeX.Document\shell\open\command";  ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\.tex\OpenWithProgids"; ValueType: string; ValueName: "QTeX.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\.bib\OpenWithProgids"; ValueType: string; ValueName: "QTeX.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}";                     ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes";      ValueType: string; ValueName: ".tex"; ValueData: ""; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes";      ValueType: string; ValueName: ".bib"; ValueData: ""; Tasks: texopenwith
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command";  ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: texopenwith

; ---- Right-click a folder (or empty space inside one) -> "Open in QTeX"
Root: HKA; Subkey: "Software\Classes\Directory\shell\QTeX";                      ValueType: string; ValueData: "Open in QTeX"; Flags: uninsdeletekey; Tasks: foldercontext
Root: HKA; Subkey: "Software\Classes\Directory\shell\QTeX";                      ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExe},0"; Tasks: foldercontext
Root: HKA; Subkey: "Software\Classes\Directory\shell\QTeX\command";              ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: foldercontext
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\QTeX";           ValueType: string; ValueData: "Open in QTeX"; Flags: uninsdeletekey; Tasks: foldercontext
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\QTeX";           ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExe},0"; Tasks: foldercontext
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\QTeX\command";   ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%V"""; Tasks: foldercontext

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer with /SILENT /RELAUNCH=1: reopen QTeX afterwards, as the user (not elevated)
Filename: "{app}\{#MyAppExe}"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
