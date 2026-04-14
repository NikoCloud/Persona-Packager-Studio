; Inno Setup script for Persona Packager Studio
; Requires Inno Setup 6+ — https://jrsoftware.org/isinfo.php
; Build: open in Inno Setup Compiler and click Compile, or: iscc installer.iss
; Output: dist\PersonaPackagerStudio_Setup.exe

#define AppName      "Persona Packager Studio"
#define AppVersion   "1.0.4"
#define AppPublisher "NikoCloud"
#define AppURL       "https://github.com/NikoCloud/Persona-Packager-Studio"
#define AppExeName   "PersonaPackagerStudio.exe"
#define SetupExeName "PersonaPackagerStudio_Setup"

[Setup]
AppId={{B2E4D3F1-5C9A-4E3B-8D7E-2F6C8B4E1A02}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename={#SetupExeName}
SetupIconFile=assets\logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
