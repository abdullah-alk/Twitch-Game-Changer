; --- Twitch Game Changer Installer Script with Auto-Update Support ---
; This installer works seamlessly with the built-in auto-updater!

#define MyAppName "Twitch Game Changer"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "M84T1"
#define MyAppExeName "TwitchGameChanger.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TwitchGameChanger
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=TwitchGameChangerinstaller
SetupIconFile=icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; Auto-update support flags - FIXED
CloseApplications=force
CloseApplicationsFilter=TwitchGameChanger.exe,pythonw.exe,python.exe
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Run at &startup"; GroupDescription: "Additional options:"

[Files]
Source: "dist\TwitchGameChanger.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; 
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--startup"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  AppWasRunning: Boolean;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create app data directory for settings
    ForceDirectories(ExpandConstant('{userappdata}\TwitchGameChanger'));
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  AttemptCount: Integer;
begin
  Result := '';
  AppWasRunning := False;
  AttemptCount := 0;
  
  // Check if app is running and try to close it properly
  while (AttemptCount < 5) do
  begin
    if FindWindowByClassName('TkTopLevel') <> 0 then
    begin
      AppWasRunning := True;
      
      // First attempt: Try graceful termination with taskkill /IM
      if AttemptCount = 0 then
      begin
        Log('Attempt ' + IntToStr(AttemptCount + 1) + ': Trying graceful close with taskkill /IM');
        Exec('taskkill', '/IM TwitchGameChanger.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Sleep(2000); // Wait 2 seconds for graceful close
      end
      // Second attempt: Force close with taskkill /F /IM
      else if AttemptCount = 1 then
      begin
        Log('Attempt ' + IntToStr(AttemptCount + 1) + ': Trying force close with taskkill /F /IM');
        Exec('taskkill', '/F /IM TwitchGameChanger.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Sleep(2000);
      end
      // Third attempt: Try pythonw.exe processes (if Python-based build)
      else if AttemptCount = 2 then
      begin
        Log('Attempt ' + IntToStr(AttemptCount + 1) + ': Trying to close pythonw.exe processes');
        Exec('taskkill', '/F /IM pythonw.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Sleep(1500);
      end
      // Fourth attempt: Try python.exe processes
      else if AttemptCount = 3 then
      begin
        Log('Attempt ' + IntToStr(AttemptCount + 1) + ': Trying to close python.exe processes');
        Exec('taskkill', '/F /IM python.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Sleep(1500);
      end
      // Final attempt: Give it one more try with full force
      else
      begin
        Log('Attempt ' + IntToStr(AttemptCount + 1) + ': Final force close attempt');
        Exec('taskkill', '/F /IM TwitchGameChanger.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Exec('taskkill', '/F /IM pythonw.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Exec('taskkill', '/F /IM python.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        Sleep(3000); // Wait longer on final attempt
      end;
      
      AttemptCount := AttemptCount + 1;
    end
    else
    begin
      // App is not running anymore, exit the loop
      Log('Application closed successfully after ' + IntToStr(AttemptCount) + ' attempts');
      Break;
    end;
  end;
  
  // If still running after all attempts, warn the user
  if FindWindowByClassName('TkTopLevel') <> 0 then
  begin
    Result := 'Unable to close Twitch Game Changer. Please close the application manually and click Retry.';
    Log('ERROR: Could not close application after ' + IntToStr(AttemptCount) + ' attempts');
  end
  else
  begin
    Log('Application successfully closed, proceeding with installation');
    // Extra safety wait
    Sleep(1000);
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  Log('Setup initialization started');
end;

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\TwitchGameChanger"
