#define AppVersion "1.3.11"

[Setup]
AppId={{948E012B-0809-42B3-88C8-B1D36E755B6C}
AppName=灵图 ART · 美术素材库
AppVersion={#AppVersion}
AppPublisher=灵图 ART
DefaultDirName={localappdata}\Programs\ARTSPACE
DefaultGroupName=灵图 ART
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\output\installer
OutputBaseFilename=LingTu-ART-Setup-{#AppVersion}
SetupIconFile=artspace.ico
UninstallDisplayIcon={app}\ARTSPACE.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
AppMutex=ARTSPACE-Desktop-Application
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："
Name: "existinglibrary"; Description: "继续使用当前已有的素材库（保留原文件位置）"; GroupDescription: "素材库："; Check: HasExistingLibrary

[Files]
Source: "..\build\ARTSPACE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "artspace.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy
Source: "桌面版使用说明.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "AI图生图使用说明.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\灵图 ART"; Filename: "{app}\ARTSPACE.exe"; IconFilename: "{app}\artspace.ico"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{autoprograms}\灵图 ART\灵图 ART"; Filename: "{app}\ARTSPACE.exe"; IconFilename: "{app}\artspace.ico"; WorkingDir: "{app}"
Name: "{autoprograms}\灵图 ART\卸载 灵图 ART"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\ARTSPACE.exe"; Description: "启动灵图 ART 美术素材库"; Flags: nowait postinstall skipifsilent

[Code]
function LegacyConfig: String;
begin
  Result := ExpandConstant('{param:LIBRARYCONFIG|{src}\config.json}');
end;

function HasExistingLibrary: Boolean;
begin
  Result := FileExists(LegacyConfig);
end;

function NeedsWebView2: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := not ((RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
                 (RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if NeedsWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := '无法启动 WebView2 运行环境安装程序。'
    else if NeedsWebView2 then
      Result := 'WebView2 运行环境尚未安装完成。请连接网络后重试安装。';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UserDir: String;
begin
  if CurStep = ssInstall then begin
    DeleteFile(ExpandConstant('{autodesktop}\Artspace Studio.lnk'));
    DeleteFile(ExpandConstant('{autoprograms}\Artspace Studio\Artspace Studio.lnk'));
    DeleteFile(ExpandConstant('{autoprograms}\Artspace Studio\卸载 Artspace Studio.lnk'));
    RemoveDir(ExpandConstant('{autoprograms}\Artspace Studio'));
    DeleteFile(ExpandConstant('{autodesktop}\ARTSPACE 美术素材库.lnk'));
  end;
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('existinglibrary') and HasExistingLibrary then begin
    UserDir := ExpandConstant('{localappdata}\ARTSPACE');
    ForceDirectories(UserDir);
    if not FileExists(UserDir + '\config.json') then
      SaveStringToFile(UserDir + '\source-library.txt', UTF8Encode(LegacyConfig), False);
  end;
end;







