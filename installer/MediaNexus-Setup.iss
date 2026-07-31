; ============================================================================
; MediaNexus 安装程序脚本（Inno Setup 6）
;
; 用法（在项目根目录下，已先执行 PyInstaller 打包出 dist\MediaNexus.exe）：
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\MediaNexus-Setup.iss
;
; 产出：dist\installer\MediaNexus-Setup.exe
;
; 特性：
;   - 检测已有安装，自动切换为「更新」模式（提示用户、保留安装路径）
;   - 用户可选择安装位置（默认 C:\Program Files\MediaNexus）
;   - 安装完成时可勾选「创建桌面快捷方式」「创建快速启动快捷方式」（默认勾选）
;   - 附带开始菜单程序组（主程序 + 用户手册 + 卸载）
;   - 卸载时不删除用户配置（%APPDATA%\MediaNexus）
; ============================================================================

#define MyAppName      "MediaNexus"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "Zxgaoq"
#define MyAppExeName   "MediaNexus.exe"
#define MyAppId        "E7A2C41F-5B3D-4E8A-9C61-2F8A3B7D1E5A"
; 打包产物相对项目根目录（本脚本在 installer\ 下，向上退一级）
#define SourceRoot     ".."
; 1.2 版安装脚本在 [Code] 中拼接键名时多了一个 }，导致注册表键名错误（双 }} ）
; 当前安装程序需检测并清理该残留条目，避免 Windows 应用列表出现重复项
#define BuggyKeyName   "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{" + MyAppId + "}}_is1"

[Setup]
; 唯一 AppId（保持同一 GUID 以便将来升级覆盖安装）。如需重置可重新生成。
AppId={{{#MyAppId}}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; 不显示「选择开始菜单文件夹」页（直接用默认组名，更贴近主流软件）
DisableProgramGroupPage=yes
; 允许不创建快捷方式（用户可在勾选时取消）
AllowNoIcons=yes
OutputDir={#SourceRoot}\dist\installer
OutputBaseFilename=MediaNexus-Setup
SetupIconFile={#SourceRoot}\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; 64 位系统装到 Program Files，32 位系统装到 Program Files (x86)
ArchitecturesInstallIn64BitMode=x64compatible
; 允许用户在安装第一步选择「为所有用户」或「仅为当前用户」安装，
; 选了「当前用户」就改走 lowest 模式，自然消除 per-user 区域警告。
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
; 简体中文 UI（如需启用）：
;   1) 从 https://jrsoftware.org/files/istrans/ 下载 ChineseSimplified-6.7.3.zip
;   2) 解压 ChineseSimplified.isl 到 C:\Program Files (x86)\Inno Setup 6\Languages\
;   3) 把下面这一行取消注释：
 Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
;
; 当前默认用英文 UI，避免某些精简版 Inno 安装缺少该文件时编译失败。
; English UI by default. See comment above to enable Chinese.

[Tasks]
; 无 Flags 即「首次安装默认勾选」；重装时 Inno 会自动记忆上次选择。
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加图标："
Name: "quicklaunchicon"; Description: "创建快速启动栏快捷方式(&Q)"; GroupDescription: "附加图标："

[Files]
; 安装 PyInstaller onedir 产出的整个目录（含 exe + 所有 DLL + assets + docs）
Source: "{#SourceRoot}\dist\MediaNexus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单程序组
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\用户手册"; Filename: "{app}\_internal\docs\MediaNexus-Manual.html"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式（勾选时创建）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; 快速启动栏快捷方式（勾选时创建，仅旧版 Windows 有意义）
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 安装完成后可选「立即运行」
Filename: "{app}\{#MyAppExeName}"; Description: "安装完成后运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  IsUpdate: Boolean;
  PrevVersion: String;
  PrevInstallDir: String;
  UpdateNoticeShown: Boolean;

function GetUninstallKeyName: String;
begin
  Result := 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{' +
    '{#MyAppId}' + '}_is1';
end;

function TryLoadPreviousInstall(const RootKey: Integer): Boolean;
var
  RegPath: String;
begin
  Result := False;
  RegPath := GetUninstallKeyName;

  if RegQueryStringValue(RootKey, RegPath, 'UninstallString', PrevInstallDir) then
  begin
    IsUpdate := True;
    PrevVersion := '未知版本';
    PrevInstallDir := '';

    RegQueryStringValue(RootKey, RegPath, 'DisplayVersion', PrevVersion);
    if RegQueryStringValue(RootKey, RegPath, 'InstallLocation', PrevInstallDir) then
      WizardForm.DirEdit.Text := PrevInstallDir;

    Result := True;
  end;
end;

function GetPreviousInstall: Boolean;
begin
  Result := TryLoadPreviousInstall(HKLM);
  if not Result then
    Result := TryLoadPreviousInstall(HKCU);
end;

procedure UpdateReadyPageText;
var
  ReadyText: String;
begin
  if IsUpdate then
  begin
    ReadyText :=
      '即将把 {#MyAppName} 从 ' + PrevVersion + ' 更新到 v{#MyAppVersion}。' + #13#10#13#10 +
      '安装位置：' + WizardForm.DirEdit.Text + #13#10 +
      '本次为覆盖安装，只会更新程序文件，不会清除现有配置、项目索引和 QC 检测缓存。';
    WizardForm.ReadyLabel.Caption := ReadyText;
  end;
end;

procedure ShowUpdateNoticeOnce;
var
  Msg: String;
begin
  if IsUpdate and (not UpdateNoticeShown) then
  begin
    Msg := '检测到已安装版本 ' + PrevVersion + '。' + #13#10#13#10 +
      '本次将执行更新安装：' + #13#10 +
      '1. 覆盖旧版本程序文件；' + #13#10 +
      '2. 保留当前安装目录；' + #13#10 +
      '3. 不会删除您的配置、项目索引和 QC 检测缓存。';
    SuppressibleMsgBox(Msg, mbInformation, MB_OK, IDOK);
    UpdateNoticeShown := True;
  end;
end;

{ 清理旧版 MediaSync 注册表残留 —— 1.2 版安装脚本拼接键名时多了一个花括号， }
{ 导致旧版条目写入了错误键名（双括号），与当前正确键名不匹配。               }
{ 不清理会导致 Windows「应用和功能」列表出现重复条目。安装向导初始化时运行。   }
procedure CleanOldMediaSyncEntries;
var
  UninstExe: String;
  ResultCode: Integer;
  KeyExists: Boolean;
begin
  { ── 阶段 1：正确键名的旧条目（1.0.x / 1.1.x） ── }
  KeyExists := RegKeyExists(HKLM, GetUninstallKeyName) or
               RegKeyExists(HKCU, GetUninstallKeyName);
  if KeyExists then
  begin
    if RegQueryStringValue(HKLM, GetUninstallKeyName, 'UninstallString', UninstExe) or
       RegQueryStringValue(HKCU, GetUninstallKeyName, 'UninstallString', UninstExe) then
    begin
      UninstExe := RemoveQuotes(UninstExe);
      if (UninstExe <> '') and FileExists(UninstExe) then
      begin
        Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;
    end;
    { 卸载程序应已自行删除注册表键；若仍存在则强制清理 }
    if RegKeyExists(HKLM, GetUninstallKeyName) then
      RegDeleteKeyIncludingSubkeys(HKLM, GetUninstallKeyName);
    if RegKeyExists(HKCU, GetUninstallKeyName) then
      RegDeleteKeyIncludingSubkeys(HKCU, GetUninstallKeyName);
  end;

  { 阶段 2：错误键名的旧条目（1.2 版双括号 bug） }
  KeyExists := RegKeyExists(HKLM, '{#BuggyKeyName}') or
               RegKeyExists(HKCU, '{#BuggyKeyName}');
  if KeyExists then
  begin
    if RegQueryStringValue(HKLM, '{#BuggyKeyName}', 'UninstallString', UninstExe) or
       RegQueryStringValue(HKCU, '{#BuggyKeyName}', 'UninstallString', UninstExe) then
    begin
      UninstExe := RemoveQuotes(UninstExe);
      if (UninstExe <> '') and FileExists(UninstExe) then
      begin
        Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;
    end;
    if RegKeyExists(HKLM, '{#BuggyKeyName}') then
      RegDeleteKeyIncludingSubkeys(HKLM, '{#BuggyKeyName}');
    if RegKeyExists(HKCU, '{#BuggyKeyName}') then
      RegDeleteKeyIncludingSubkeys(HKCU, '{#BuggyKeyName}');
  end;
end;

procedure InitializeWizard;
begin
  IsUpdate := False;
  PrevVersion := '';
  PrevInstallDir := '';
  UpdateNoticeShown := False;

  { 安装前先清理旧版 MediaSync 注册表残留（防止应用列表出现重复条目） }
  CleanOldMediaSyncEntries;

  GetPreviousInstall;

  if IsUpdate then
  begin
    { 更新模式：标题、欢迎页、按钮文本 }
    WizardForm.Caption := '{#MyAppName} - 版本更新';
    WizardForm.WelcomeLabel1.Caption :=
      '即将更新 {#MyAppName} 到 v{#MyAppVersion}';
    WizardForm.WelcomeLabel2.Caption :=
      '检测到已安装版本 ' + PrevVersion + '。' +
      '这是一次覆盖更新安装，您的个人数据（配置、索引、检测缓存）会继续保留。';
    UpdateReadyPageText;
    { 向导按钮文本 }
    WizardForm.NextButton.Caption := '下一步';
    WizardForm.FinishedHeadingLabel.Caption :=
      '{#MyAppName} v{#MyAppVersion} 更新完成';
  end
  else
  begin
    { 全新安装：默认文案不动，仅微调 }
    WizardForm.Caption := '{#MyAppName} - 安装向导';
    WizardForm.WelcomeLabel1.Caption :=
      '欢迎安装 {#MyAppName} v{#MyAppVersion}';
    WizardForm.WelcomeLabel2.Caption :=
      '影视全行业素材同步 + 视频质检工具。' +
      '本安装包内置完整版 FFmpeg，开箱即用。';
    WizardForm.FinishedHeadingLabel.Caption :=
      '{#MyAppName} v{#MyAppVersion} 安装完成';
  end;
end;

{ 自定义安装确认页文本（更新时显示不同提示） }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    ShowUpdateNoticeOnce;
  end
  else if CurPageID = wpReady then
  begin
    if IsUpdate then
    begin
      UpdateReadyPageText;
      WizardForm.ReadyMemo.Lines.Insert(0,
        '━━━━━━━━━━━━━━━━━━━━━━━━');
      WizardForm.ReadyMemo.Lines.Insert(0,
        '更新安装：将覆盖旧版本程序文件，现有配置与缓存会保留。');
      WizardForm.ReadyMemo.Lines.Insert(0,
        '━━━━━━━━━━━━━━━━━━━━━━━━');
    end;
  end
  else if CurPageID = wpFinished then
  begin
    if IsUpdate then
      WizardForm.FinishedLabel.Caption :=
        '{#MyAppName} 已从 ' + PrevVersion + ' 更新到 v{#MyAppVersion}。' +
        '您的配置、项目索引和 QC 检测缓存均已保留，可直接继续使用。';
  end;
end;
