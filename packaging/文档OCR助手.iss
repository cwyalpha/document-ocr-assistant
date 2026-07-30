#ifndef SourceRoot
  #error SourceRoot must be supplied with /DSourceRoot=...
#endif
#ifndef InstallerOutput
  #define InstallerOutput "."
#endif

[Setup]
AppId={{B94C3D14-7C90-4F0D-B319-5BFF88E10F62}
AppName=文档OCR助手
AppVersion=0.1.1
AppPublisher=DocumentOCR
DefaultDirName={localappdata}\Programs\文档OCR助手
DefaultGroupName=文档OCR助手
PrivilegesRequired=lowest
OutputDir={#InstallerOutput}
OutputBaseFilename=文档OCR助手-Windows-x86_64-安装程序
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourceRoot}\assets\app-icon.ico
UninstallDisplayIcon={app}\app\文档OCR助手.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\文档OCR助手"; Filename: "{app}\app\文档OCR助手.exe"
Name: "{autodesktop}\文档OCR助手"; Filename: "{app}\app\文档OCR助手.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Run]
Filename: "{app}\app\文档OCR助手.exe"; Description: "启动文档OCR助手"; Flags: nowait postinstall skipifsilent
