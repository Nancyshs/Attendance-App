; Uses the Python and MySQL already installed on the PC.
#define MyAppName "Attendance"
#define MyAppVersion "1.3"

[Setup]
AppId={{B2C4D6E8-1A33-4F70-8C19-5D4E3F2A1B90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\Attendance
DefaultGroupName=Attendance
DisableProgramGroupPage=yes
OutputDir=..\..\..
OutputBaseFilename=Attendance_Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Attendance
SetupLogging=yes
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Setup finished.%n%nOpen "الحضور والتقييم" on the desktop.%n%nSign in as admin with the password you chose.

[Files]
Source: "staging\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{app}\backend\data"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{group}\الحضور والتقييم"; Filename: "{app}\Run.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\الحضور والتقييم"; Filename: "{app}\Run.bat"; WorkingDir: "{app}"

[Code]
var
  MysqlPage: TInputQueryWizardPage;
  AdminPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  MysqlPage := CreateInputQueryPage(wpSelectDir,
    'MySQL',
    'MySQL root password',
    'Enter the MySQL root password.' + #13#10 +
    'ادخل كلمة مرور root الخاصة بـ MySQL.' + #13#10 +
    'MySQL must already be installed. This setup does not install it.' + #13#10 +
    'لو root من غير كلمة سر، سيب الخانة فاضية.');
  MysqlPage.Add('Password:', True);

  AdminPage := CreateInputQueryPage(MysqlPage.ID,
    'Administrator',
    'Create the program password',
    'Choose a password for the admin account.' + #13#10 +
    'اختار كلمة مرور حساب المدير داخل البرنامج.');
  AdminPage.Add('Password:', True);
  AdminPage.Add('Confirm password:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = AdminPage.ID then
  begin
    if Trim(AdminPage.Values[0]) = '' then
    begin
      MsgBox('Choose the admin password.', mbError, MB_OK);
      Result := False;
    end
    else if AdminPage.Values[0] <> AdminPage.Values[1] then
    begin
      MsgBox('The admin password and confirmation do not match.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Params: String;
  ResultCode: Integer;
  PassFile, AdminFile: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  PassFile := ExpandConstant('{tmp}\mysql-password.txt');
  AdminFile := ExpandConstant('{tmp}\admin-password.txt');
  SaveStringToFile(PassFile, MysqlPage.Values[0], False);
  SaveStringToFile(AdminFile, AdminPage.Values[0], False);
  Params :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\installer\configure.ps1') + '"' +
    ' -AppDir "' + ExpandConstant('{app}') + '"' +
    ' -PasswordFile "' + PassFile + '"' +
    ' -AdminPasswordFile "' + AdminFile + '"';

  WizardForm.StatusLabel.Caption := 'Connecting to MySQL and preparing the program. Please wait...';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Could not start setup. See installer\setup.log.', mbError, MB_OK);
    Exit;
  end;
  if ResultCode <> 0 then
    MsgBox('Setup could not finish. Open ' + ExpandConstant('{app}\installer\setup.log'), mbError, MB_OK);
end;
