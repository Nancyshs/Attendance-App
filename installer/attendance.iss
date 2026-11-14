; Double-click installer. The user only presses Next.
[Setup]
AppId={{A7B1C3E2-6D44-4F18-9A20-6E5B1C0A77D4}
AppName=Attendance
AppVersion=1.1
AppPublisher=Attendance
DefaultDirName=C:\Attendance
UsePreviousAppDir=yes
DisableDirPage=auto
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\..
OutputBaseFilename=Attendance_Setup
UninstallDisplayName=Attendance
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=Click Next. If the program is already installed, it will be updated and the saved data will stay.
FinishedHeadingLabel=The program is ready
FinishedLabel=Click Finish.

[Files]
Source: "staging\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deploy\uninstall.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "StopAttendance"

[Code]
var
  Upgrading: Boolean;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Upgrading := DirExists(ExpandConstant('{app}\backend'));
  Exec(ExpandConstant('{sys}\net.exe'), 'stop AttendanceApp', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\net.exe'), 'stop AttendanceDB', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if Upgrading then
      WizardForm.StatusLabel.Caption := 'Updating the program. Please wait...'
    else
      WizardForm.StatusLabel.Caption := 'Setting up the program. Please wait...';
    WizardForm.ProgressGauge.Style := npbstMarquee;
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      ExpandConstant('-NoProfile -ExecutionPolicy Bypass -File "{app}\deploy\first_run.ps1"'),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('Setup could not finish. Open ' + ExpandConstant('{app}\logs\install.log'), mbError, MB_OK);
  end;
end;
