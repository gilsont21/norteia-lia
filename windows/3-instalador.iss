; Instalador do Norteia Lia (Inno Setup, gratuito: jrsoftware.org).
; Antes: rode 2-criar-exe.bat para gerar a pasta dist\NorteiaLia.
[Setup]
AppName=Norteia Lia
AppVersion=0.7.0
AppPublisher=LIA
DefaultDirName={autopf}\Norteia Lia
DefaultGroupName=Norteia Lia
OutputBaseFilename=Instalar-NorteiaLia
OutputDir=..\dist
SetupIconFile=norteia.ico
UninstallDisplayIcon={app}\NorteiaLia.exe
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
Source: "..\dist\NorteiaLia\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Norteia Lia"; Filename: "{app}\NorteiaLia.exe"
Name: "{autodesktop}\Norteia Lia"; Filename: "{app}\NorteiaLia.exe"; Tasks: icone

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Norteia Lia"; \
    ValueData: """{app}\NorteiaLia.exe"" --minimizado"; Flags: uninsdeletevalue; Tasks: iniciar

[Run]
Filename: "{app}\NorteiaLia.exe"; Description: "Abrir o Norteia Lia agora"; Flags: nowait postinstall skipifsilent
