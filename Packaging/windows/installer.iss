; Compile only through build.ps1, which generates an exact [Files] include.
#ifndef StageDir
  #error StageDir is required
#endif
#ifndef FilesInclude
  #error FilesInclude is required
#endif
[Setup]
AppId=ARCHONStudioPortable1
AppName=ARCHON Studio
AppVersion=1.0.0
DefaultDirName={localappdata}\ARCHON Studio
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ARCHON-Studio-1.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=ARCHON Studio
[Files]
#include FilesInclude
[Icons]
Name: "{userprograms}\ARCHON Studio"; Filename: "{app}\Runtime\python\pythonw.exe"; Parameters: "-B ""{app}\Tools\archon_windows_launch.py"""; WorkingDir: "{app}"
; No wildcard cleanup: generated Results, Config, Atlas and public assets survive uninstall.
