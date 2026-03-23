# Cosplay + Claude Code - Uninstall (called by uninstall.cmd)
$ErrorActionPreference = 'Continue'

$install = Join-Path $env:LOCALAPPDATA 'Cosplay'
$pyDir   = Join-Path $env:LOCALAPPDATA 'CosplayPython'
$nodeDir = Join-Path $env:LOCALAPPDATA 'CosplayNode'
$cosplayCfg = Join-Path $HOME '.cosplay'
$claudeCfg  = Join-Path $HOME '.claude'

# ---------------------------------------------------------------------------
function Stop-CosplayServer {
    $killed = 0
    try {
        $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*cosplay.py*' }
        foreach ($p in $procs) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            $killed++
        }
    } catch { }
    if ($killed -gt 0) { Write-Host "  [ OK ] Stopped $killed Cosplay server process(es)" }
    else               { Write-Host '  [ OK ] No Cosplay server running' }
}

function Remove-UserPathEntry([string[]]$dirs) {
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    if ($null -eq $key) { return }
    $current = $key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    if ($null -eq $current) { $key.Close(); return }
    $raw = [string]$current
    $literal = "%LocalAppData%"
    $parts = $raw.Split(';')
    $keep = @()
    foreach ($part in $parts) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        $matched = $false
        foreach ($d in $dirs) {
            if ([string]::Equals($part.TrimEnd('\'), $d.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { $matched = $true; break }
            $lit = Join-Path $literal ($d.Substring($env:LOCALAPPDATA.Length).TrimStart('\'))
            if ([string]::Equals($part.TrimEnd('\'), $lit.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { $matched = $true; break }
        }
        if (-not $matched) { $keep += $part }
    }
    $new = $keep -join ';'
    if ($new -ne $raw) {
        $key.SetValue('Path', $new, [Microsoft.Win32.RegistryValueKind]::ExpandString)
        Write-Host '  [ OK ] Updated user PATH'
    }
    $key.Close()
}

function Ask-Keep([string]$title) {
    $ans = Read-Host "Keep $title ? [y/N]"
    return ($ans -match '^[yY]')
}

function Restore-ClaudeSettings {
    $file = Join-Path $HOME '.claude\settings.json'
    if (-not (Test-Path $file)) { return }
    try {
        $data = Get-Content $file -Raw | ConvertFrom-Json
        if ($null -eq $data.env -or $null -eq $data.env.PSObject) { return }
        $keep = @{}
        $token = 'cosplay-secret-token'
        try {
            $rtFile = Join-Path $HOME '.cosplay\runtime.json'
            if (Test-Path $rtFile) {
                $rt = Get-Content $rtFile -Raw | ConvertFrom-Json
                if ($rt.api_auth_token) { $token = [string]$rt.api_auth_token }
            }
        } catch { }
        foreach ($prop in $data.env.PSObject.Properties) {
            $drop = $false
            switch ($prop.Name) {
                'ANTHROPIC_BASE_URL' { $drop = ($prop.Value -match '^http://127\.0\.0\.1:\d+/?$') }
                'ANTHROPIC_AUTH_TOKEN' { $drop = ([string]$prop.Value -eq $token) }
                'ANTHROPIC_MODEL' { $drop = ($prop.Value -eq 'claude-cosplay-default') }
                'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY' { $drop = ([string]$prop.Value -eq '1') }
                'CLAUDE_CODE_AUTO_COMPACT_WINDOW' { $drop = ([string]$prop.Value -eq '190000') }
                'NO_PROXY' { $drop = ($prop.Value -eq '127.0.0.1,localhost,::1') }
            }
            if (-not $drop) { $keep[$prop.Name] = $prop.Value }
        }
        if ($keep.Count -eq 0) {
            $data.PSObject.Properties.Remove('env')
        } else {
            $data.env = [PSCustomObject]$keep
        }
        $json = $data | ConvertTo-Json -Depth 10
        [IO.File]::WriteAllText($file, $json, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host '  [ OK ] ~/.claude/settings.json restored'
    } catch { }
}

# ---------------------------------------------------------------------------
Clear-Host
Write-Host '============================================================'
Write-Host '                 Cosplay v3.9  | Uninstall'
Write-Host '============================================================'
Write-Host ''

Stop-CosplayServer
Write-Host ''

# ---------------------------------------------------------------------------
# 4 separate keep/remove prompts
# ---------------------------------------------------------------------------
$keepCosplay = Ask-Keep 'Cosplay'
$keepClaude  = Ask-Keep 'Claude Code'
$keepPy      = if (Test-Path $pyDir)   { Ask-Keep 'Python' }   else { $true }
$keepNode    = if (Test-Path $nodeDir) { Ask-Keep 'Node.js' }  else { $true }

Write-Host ''

# ---------------------------------------------------------------------------
# Claude Code (npm package + ~/.claude data)
# ---------------------------------------------------------------------------
if (-not $keepClaude) {
    Write-Host '  [   ] Uninstalling Claude Code...'
    & npm.cmd uninstall -g @anthropic-ai/claude-code *>> $null
    Remove-Item -LiteralPath $claudeCfg -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "$HOME\.claude.json" -Force -ErrorAction SilentlyContinue
    Write-Host '  [ OK ] Claude Code removed'
} else {
    Write-Host '  [ OK ] Keeping Claude Code'
}

# ---------------------------------------------------------------------------
# PATH cleanup
# ---------------------------------------------------------------------------
$pathToStrip = @()
if (-not $keepCosplay) { $pathToStrip += $install }
if (-not $keepPy)      { $pathToStrip += $pyDir; $pathToStrip += "$pyDir\Scripts" }
if (-not $keepNode)    { $pathToStrip += $nodeDir }
Remove-UserPathEntry $pathToStrip
Restore-ClaudeSettings

# ---------------------------------------------------------------------------
# Config + folders
# ---------------------------------------------------------------------------
$desktop = [Environment]::GetFolderPath('Desktop')
$desktopShortcut = Join-Path $desktop 'cclaude.lnk'
if (-not $keepCosplay) {
    Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
    Write-Host '  [ OK ] Desktop shortcut removed'
}
if (-not $keepCosplay) {
    Remove-Item -LiteralPath $cosplayCfg -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host '  [ OK ] Cosplay config + API key removed'
}
if (-not $keepPy)   { Remove-Item -LiteralPath $pyDir   -Recurse -Force -ErrorAction SilentlyContinue }
if (-not $keepNode) { Remove-Item -LiteralPath $nodeDir -Recurse -Force -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Clear-Host
Write-Host '============================================================'
Write-Host '                 Cosplay v3.9  | Uninstall'
Write-Host '============================================================'
Write-Host ''
if ($keepCosplay) { Write-Host '  [ OK ] Cosplay kept' } else { Write-Host '  [ OK ] Cosplay removed' }
if ($keepClaude)  { Write-Host '  [ OK ] Claude Code kept' } else { Write-Host '  [ OK ] Claude Code removed' }
if ($keepPy)      { Write-Host '  [ OK ] Python kept' } else { Write-Host '  [ OK ] Python removed' }
if ($keepNode)    { Write-Host '  [ OK ] Node.js kept' } else { Write-Host '  [ OK ] Node.js removed' }
if ($keepCosplay) { Write-Host '  [ OK ] Desktop shortcut kept' } else { Write-Host '  [ OK ] Desktop shortcut removed' }
Write-Host '  [ OK ] PATH cleaned'
Write-Host ''
Write-Host '------------------------------------------------------------'
Write-Host '          Uninstall Finished !!!'
Write-Host '------------------------------------------------------------'
Write-Host ''
Write-Host '============================================================'
Write-Host ''

# ---------------------------------------------------------------------------
# Self-delete the install folder (we run from inside it)
# ---------------------------------------------------------------------------
if (-not $keepCosplay) {
    $cleanup = Join-Path $env:TEMP 'cosplay-rm.cmd'
    @"
@echo off
ping -n 3 127.0.0.1 >nul
rmdir /s /q "$install" >nul 2>nul
del "%~f0" >nul 2>nul
"@ | Set-Content -Path $cleanup -Encoding ASCII
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', "`"$cleanup`"" -WindowStyle Hidden
}

Read-Host 'Press any key to exit...'
