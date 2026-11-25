; Instalador do Kaguya Studio (Inno Setup 6, gratuito).
; - instala só para o usuário atual (sem pedir administrador) em %LOCALAPPDATA%\Programs\Kaguya Studio
; - o MESMO instalador de uma versão nova atualiza a instalação existente: fecha o Studio aberto
;   (KaguyaStudio.exe --sair), troca os arquivos e mantém seus dados (%LOCALAPPDATA%\KaguyaStudio)
; - desinstalar remove o programa; seus dados, projetos e configurações ficam guardados
; Compilado no CI:  iscc /DAppVersion=4.9.0 /DSourceDir=..\dist\KaguyaStudio instalador\KaguyaStudio.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\KaguyaStudio"
#endif

[Setup]
AppId={{AD84F6BC-4248-4CD5-B234-F8FACAD3C99D}
AppName=Kaguya Studio
AppVersion={#AppVersion}
AppVerName=Kaguya Studio {#AppVersion}
AppPublisher=Kaguya Studio
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Kaguya Studio
DefaultGroupName=Kaguya Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=KaguyaStudio-Instalador-{#AppVersion}
SetupIconFile=..\assets\branding\kaguya.ico
UninstallDisplayIcon={app}\KaguyaStudio.exe
UninstallDisplayName=Kaguya Studio
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "startup"; Description: "Iniciar com o Windows (fica na bandeja, perto do relógio)"; GroupDescription: "Opções:"; Flags: unchecked

[InstallDelete]
; a pasta de bibliotecas é trocada inteira numa atualização (evita arquivos velhos misturados)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Kaguya Studio"; Filename: "{app}\KaguyaStudio.exe"
Name: "{autodesktop}\Kaguya Studio"; Filename: "{app}\KaguyaStudio.exe"; Tasks: desktopicon
Name: "{userstartup}\Kaguya Studio"; Filename: "{app}\KaguyaStudio.exe"; Parameters: "--segundo-plano"; Tasks: startup

[Run]
Filename: "{app}\KaguyaStudio.exe"; Description: "Abrir o Kaguya Studio agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\KaguyaStudio.exe"; Parameters: "--sair"; Flags: runhidden waituntilterminated; RunOnceId: "FecharStudio"

[Code]
// Before copying files: ask a running Kaguya Studio (possibly hidden in the tray) to exit.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  Exe: String;
begin
  Result := '';
  Exe := ExpandConstant('{app}\KaguyaStudio.exe');
  if FileExists(Exe) then
  begin
    Exec(Exe, '--sair', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(1500);
  end;
end;
