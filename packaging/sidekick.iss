; Sidekick's installer (M24), built by packaging/build.py with Inno Setup 6.
;
; For each Windows user, no admin: the program goes to %LOCALAPPDATA%\Programs\Sidekick, with a
; Start menu entry, an optional Desktop shortcut and an entry in Windows' installed apps.
; Microsoft's WebView2 runtime (the window Sidekick draws in) is installed only if it's missing.
; Updates run this quietly (/VERYSILENT): it waits for Sidekick to close, replaces the program
; files and opens Sidekick again. Each user's own files (%LOCALAPPDATA%\Sidekick: settings,
; keys, champion lists, reports) are never touched, except on uninstall if the user says so.
; Not code-signed on purpose (DECISIONS #116): Windows asks once before the first run.

#ifndef AppVersion
  #define AppVersion "0.0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Sidekick"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef WebView2
  #define WebView2 "..\build\packaging\MicrosoftEdgeWebview2Setup.exe"
#endif

[Setup]
; The AppId never changes: it's how Windows knows a new version replaces the old one.
AppId={{C1287DC3-2395-4276-89B3-13DCE35660DC}
AppName=Sidekick
AppVersion={#AppVersion}
AppVerName=Sidekick {#AppVersion}
AppPublisher=Sidekick
AppPublisherURL=https://github.com/zchristensen01/sidekick
AppSupportURL=https://github.com/zchristensen01/sidekick#readme
AppUpdatesURL=https://github.com/zchristensen01/sidekick/releases
AppCopyright=Sidekick contributors
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Sidekick
VersionInfoDescription=Sidekick installer
DefaultDirName={autopf}\Sidekick
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=SidekickSetup
SetupIconFile=..\scout\app\sidekick.ico
UninstallDisplayIcon={app}\Sidekick.exe
UninstallDisplayName=Sidekick
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no
RestartApplications=no
SetupMutex=SidekickSetupRunning

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Sidekick is installed. Open it from the Start menu or the Desktop, and leave it open while you play.

[Tasks]
Name: "desktopicon"; Description: "Put Sidekick on the Desktop"; GroupDescription: "Shortcuts:"

[InstallDelete]
; An update starts from a clean program folder, so files an older version had can't linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebView2}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{autoprograms}\Sidekick"; Filename: "{app}\Sidekick.exe"; AppUserModelID: "Sidekick.Scout"; Comment: "Pre-game scouting for League of Legends"
Name: "{autodesktop}\Sidekick"; Filename: "{app}\Sidekick.exe"; AppUserModelID: "Sidekick.Scout"; Comment: "Pre-game scouting for League of Legends"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 (the window Sidekick draws in)..."; Check: NeedsWebView2; Flags: waituntilterminated
; No skipifsilent: after a quiet update Sidekick opens again by itself.
Filename: "{app}\Sidekick.exe"; Description: "Open Sidekick now"; Flags: nowait postinstall

[Code]
const
  { The app holds this while it's open (scout/app/main.py, MUTEX). }
  AppMutexName = 'Local\SidekickScoutApp';
  WebView2Client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasRuntime(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

{ Microsoft's documented check: the runtime's version under any of these three keys. }
function NeedsWebView2: Boolean;
begin
  Result := not (HasRuntime(HKLM, 'SOFTWARE\WOW6432Node\' + WebView2Client)
    or HasRuntime(HKLM, 'SOFTWARE\' + WebView2Client)
    or HasRuntime(HKCU, 'Software\' + WebView2Client));
end;

function SidekickOpen: Boolean;
begin
  Result := CheckForMutexes(AppMutexName);
end;

{ A quiet update starts while the app is still closing: wait up to a minute for it. }
function WaitForSidekick(Seconds: Integer): Boolean;
var
  Tries: Integer;
begin
  Tries := 0;
  while SidekickOpen and (Tries < Seconds * 4) do
  begin
    Sleep(250);
    Tries := Tries + 1;
  end;
  Result := not SidekickOpen;
end;

function AskToClose(Silent: Boolean): Boolean;
begin
  Result := True;
  if Silent then
  begin
    Result := WaitForSidekick(60);
    Exit;
  end;
  while SidekickOpen do
    if MsgBox('Sidekick is open. Close its window (and finish your game first), then click OK.',
              mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
end;

function InitializeSetup(): Boolean;
begin
  Result := AskToClose(WizardSilent);
end;

function InitializeUninstall(): Boolean;
begin
  Result := AskToClose(UninstallSilent);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Folder: String;
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Folder := ExpandConstant('{localappdata}\Sidekick');
    if DirExists(Folder) then
      if MsgBox('Sidekick is removed. Also delete your Sidekick settings, keys, champion lists, '
                + 'reports and downloaded data?' + #13#10 + Folder + #13#10#13#10
                + 'Choose No to keep them for a later install.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Folder, True, True, True);
  end;
end;
