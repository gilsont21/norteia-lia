; Instalador do Norteia (Inno Setup, gratuito: jrsoftware.org).
; Antes: rode 2-criar-exe.bat para gerar a pasta dist\Norteia.
[Setup]
AppName=Norteia
AppVersion=0.7.0
AppPublisher=LIA
DefaultDirName={autopf}\Norteia
DefaultGroupName=Norteia
OutputBaseFilename=Instalar-Norteia
OutputDir=..\dist
SetupIconFile=norteia.ico
UninstallDisplayIcon={app}\Norteia.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "icone"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "iniciar"; Description: "Abrir junto com o Windows (recomendado, para os lembretes nunca falharem)"; GroupDescription: "Lembretes:"

[Files]
Source: "..\dist\Norteia\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Norteia"; Filename: "{app}\Norteia.exe"
Name: "{autodesktop}\Norteia"; Filename: "{app}\Norteia.exe"; Tasks: icone

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Norteia"; \
    ValueData: """{app}\Norteia.exe"" --minimizado"; Flags: uninsdeletevalue; Tasks: iniciar

[Run]
Filename: "{app}\Norteia.exe"; Description: "Abrir o Norteia agora"; Flags: nowait postinstall skipifsilent
