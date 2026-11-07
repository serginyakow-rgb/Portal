; Установщик «Портал нотариальной конторы» (Inno Setup 6).
; Собирается скриптом desktop/build.py, готовый файл — desktop/output/Portal-Setup-*.exe.
;
; Установка идёт в профиль пользователя ({localappdata}\Programs\NotaryPortal),
; права администратора не нужны. База portal.db, папка backups/, .env и журнал
; лежат рядом с Portal.exe и переживают переустановку: установщик их не трогает.

#define AppName "Портал нотариальной конторы"
#define AppShortName "Portal"
#define AppPublisher "Нотариальная контора"
#define AppExeName "Portal.exe"
; Версию передаёт build.py ключом /DAppVersion=...
#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
; Идентификатор приложения: по нему Windows узнаёт повторную установку
AppId={{7C1F5A24-93D8-4F6B-B7E1-2A0D5C8E4F63}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\NotaryPortal
DisableDirPage=auto
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Установка в профиль пользователя: папка программы остаётся доступной для записи
; (портал хранит базу, резервные копии и настройки рядом с exe)
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=Portal-Setup-{#AppVersion}
SetupIconFile=portal.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 64-битная сборка Python: на 32-битной Windows портал не запустится
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Перед установкой закрываем работающий портал (файлы exe и _internal заняты)
CloseApplications=yes
RestartApplications=no
; Значок установщика и окна «Программы и компоненты»
AllowNoIcons=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "autostart"; Description: "Запускать портал при входе в Windows (значок в трее)"; GroupDescription: "Автозапуск:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "removedata"; Description: "При удалении программы удалить базу, настройки и резервные копии"; GroupDescription: "Удаление:"; Flags: unchecked

[Files]
Source: "dist\Portal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "Портал нотариальной конторы"
Name: "{group}\{#AppName} — создать администратора"; Filename: "{app}\{#AppExeName}"; Parameters: "--create-admin"; WorkingDir: "{app}"; Comment: "Создать вход нотариуса в портал"
Name: "{group}\Папка портала (база и копии)"; Filename: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; Автозапуск портала при входе в Windows: значок сразу оказывается в трее
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "NotaryPortal"; ValueData: """{app}\{#AppExeName}"" --autostart"; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
; После установки портал запускается сам и остаётся в трее: браузер не открывается
Filename: "{app}\{#AppExeName}"; Parameters: "--no-browser"; Description: "Запустить портал сейчас (значок в трее)"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Данные удаляются только по явно отмеченному пункту: по умолчанию база,
; настройки и резервные копии остаются (их можно забрать вручную)
Type: filesandordirs; Name: "{app}"; Tasks: removedata

[Code]
{ Закрывает работающий портал: иначе установщик не сможет заменить Portal.exe }
procedure StopRunningPortal();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#AppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopRunningPortal();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopRunningPortal();
end;
