[Setup]
AppId=MuseLandscapeStudio
AppName=Muse Landscape Studio
AppVersion=1.3.2
AppVerName=Muse Landscape Studio 1.3.2
AppPublisher=FrameWeaver Community Build
DefaultDirName=D:\Code\MuseLandscapeStudio\App
UsePreviousAppDir=no
DefaultGroupName=Muse Landscape Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=Muse-Landscape-Studio-1.3.2-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app-icon.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\MuseLandscapeStudio.exe
CloseApplications=yes
AppMutex=Local\FrameWeaverWindowsPreview
AllowNoIcons=yes
Uninstallable=not IsPortable

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\MuseLandscapeStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README-Windows.vi.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "RELEASE-1.3.2.vi.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Muse Landscape Studio"; Filename: "{app}\MuseLandscapeStudio.exe"
Name: "{group}\Muse Landscape Studio (Browser mode)"; Filename: "{app}\MuseLandscapeStudio.exe"; Parameters: "--browser"
Name: "{group}\Kiem tra cap nhat Muse Landscape Studio"; Filename: "{app}\MuseLandscapeStudio.exe"; Parameters: "--check-update"
Name: "{userdesktop}\Muse Landscape Studio"; Filename: "{app}\MuseLandscapeStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MuseLandscapeStudio.exe"; Description: "Open Muse Landscape Studio"; Flags: nowait postinstall skipifsilent
Filename: "{app}\MuseLandscapeStudio.exe"; Flags: nowait skipifnotsilent

[Code]
function IsPortable: Boolean;
begin
  Result := ExpandConstant('{param:PORTABLE|0}') = '1';
end;




