# Cosplay + Claude Code - Full Setup (called by cclaude-setup.bat / the SFX)
$ErrorActionPreference = 'Continue'

$root = $PSScriptRoot
$log  = Join-Path $root 'setup.log'
if (Test-Path $log) { Remove-Item -Force $log }

$curl = "$env:SystemRoot\System32\curl.exe"
if (-not (Test-Path $curl)) { $curl = 'curl.exe' }


# ---------------------------------------------------------------------------
function Refresh-ProcessPath {
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $env:PATH = ($u + ';' + $m)
}

function Add-ToUserPath([string[]]$dirs) {
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    foreach ($d in $dirs) {
        if (($u -split ';') -notcontains $d) { $u = "$d;$u" }
    }
    [Environment]::SetEnvironmentVariable('Path', $u, 'User')
    Refresh-ProcessPath
}

function Fail([string]$msg) {
    Write-Host ''
    Write-Host "  [ERROR] $msg"
    Write-Host "  See: $log"
    Read-Host 'Press any key to exit...'
    exit 1
}

# ---------------------------------------------------------------------------
function Invoke-Step {
    param([string]$Message, [string]$FilePath, [string[]]$CmdArgs, [string]$OutLog, [scriptblock]$Verify)
    Write-Host "  [   ] $Message" -NoNewline
    $p = Start-Process -FilePath $FilePath -ArgumentList $CmdArgs `
        -WorkingDirectory $root -NoNewWindow -PassThru `
        -RedirectStandardOutput $OutLog -RedirectStandardError "$OutLog.err"
    $frames = '|', '/', '-', '\'
    $i = 0
    while (-not $p.HasExited) {
        Write-Host "`r  [ $($frames[$i % 4]) ] $Message" -NoNewline
        $i++
        Start-Sleep -Milliseconds 150
    }
    $ok = ($p.ExitCode -eq 0)
    if (-not $ok -and $Verify) {
        try { $ok = [bool](& $Verify) } catch { $ok = $false }
    }
    if ($ok) {
        Write-Host "`r  [ OK ] $Message"
        return $true
    }
    Write-Host "`r  [FAIL] $Message"
    return $false
}

function Get-PythonExe {
    foreach ($t in @('py -3.14', 'py -3.13', 'py -3.12', 'py -3.11', 'py -3', 'python')) {
        $exe = ($t -split ' ')[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $rest = if ($t -match ' ') { ($t -split ' ', 2)[1] } else { '' }
        try {
            $out = & $exe $rest -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
        } catch { }
    }
    return $null
}

function Get-NodeMajor {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { return $null }
    try {
        $o = & node --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $o -match '^v(\d+)') { return [int]$Matches[1] }
    } catch { }
    return $null
}

function Invoke-Download {
    param([string]$Message, [string]$Url, [string]$Out, [int]$MinKB = 500)
    Write-Host "  [   ] $Message" -NoNewline
    $job = Start-Job -ScriptBlock {
        param($u, $o, $k, $c)
        for ($i = 0; $i -lt 3; $i++) {
            if (Test-Path $o) { Remove-Item -Force $o }
            try {
                & $c -sSL --retry 2 --retry-all-errors --retry-delay 2 -o $o $u 2>$null
                if ($LASTEXITCODE -eq 0 -and (Test-Path $o) -and ((Get-Item $o).Length -gt ($k * 1KB))) { return $true }
            } catch { }
            Start-Sleep -Seconds 2
        }
        try {
            if (Test-Path $o) { Remove-Item -Force $o }
            Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing -TimeoutSec 120
            if ((Test-Path $o) -and ((Get-Item $o).Length -gt ($k * 1KB))) { return $true }
        } catch { }
        return $false
    } -ArgumentList $Url, $Out, $MinKB, $curl
    $frames = '|', '/', '-', '\'
    $i = 0
    while ($job.State -eq 'Running') {
        Write-Host "`r  [ $($frames[$i % 4]) ] $Message" -NoNewline
        $i++
        Start-Sleep -Milliseconds 150
    }
    $ok = $false
    try { $ok = [bool](Receive-Job -Job $job -Keep:$false) } catch { $ok = $false }
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    if ($ok) {
        Write-Host "`r  [ OK ] $Message"
        return $true
    }
    Write-Host "`r  [FAIL] $Message"
    Write-Host "  [ERROR] Download failed: $Url"
    return $false
}

function Ensure-Pip([string]$py) {
    $gp = Join-Path $root 'get-pip.py'
    if (-not (Invoke-Download 'Downloading pip installer' 'https://bootstrap.pypa.io/get-pip.py' $gp 1)) { return $false }
    & $py $gp --no-warn-script-location *>> $log
    $code = $LASTEXITCODE
    Remove-Item -Force $gp -ErrorAction SilentlyContinue
    if ($code -ne 0) { return $false }
    & $py -m pip --version 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Install-PortablePython {
    $dir = Join-Path $env:LOCALAPPDATA 'CosplayPython'
    $zip = Join-Path $root 'python-embed.zip'
    if (Test-Path $zip) { Remove-Item -Force $zip }
    $ok = Invoke-Download 'Downloading portable Python 3.11' 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' $zip
    if (-not $ok) { return $null }
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Expand-Archive -Force $zip $dir
    Remove-Item -Force $zip

    $pth = Join-Path $dir 'python311._pth'
    if (Test-Path $pth) {
        (Get-Content $pth -Raw) -replace '(?m)^#\s*import site', 'import site' | Set-Content $pth
    }
    if (-not (Ensure-Pip (Join-Path $dir 'python.exe'))) { return $null }

    Add-ToUserPath @($dir, "$dir\Scripts")
    return (Join-Path $dir 'python.exe')
}

function Install-PortableNode {
    $dir = Join-Path $env:LOCALAPPDATA 'CosplayNode'
    $ver = '22.23.2'
    $zip = Join-Path $root 'node.zip'
    if (Test-Path $zip) { Remove-Item -Force $zip }
    $ok = Invoke-Download 'Downloading portable Node.js 22' "https://nodejs.org/dist/v$ver/node-v$ver-win-x64.zip" $zip
    if (-not $ok) { return $null }
    $extract = Join-Path $root 'NodeExtract'
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Expand-Archive -Force $zip $extract
    Move-Item -Force (Join-Path $extract "node-v$ver-win-x64") $dir
    Remove-Item -Recurse -Force $extract
    Remove-Item -Force $zip

    Add-ToUserPath @($dir)
    return (Join-Path $dir 'node.exe')
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
Clear-Host
Write-Host '------------------------------------------------------------'
Write-Host '============================================================'
Write-Host '                 Cosplay v3.9  | Full Setup'
Write-Host '============================================================'
Write-Host ''
Write-Host 'Installing to:'
Write-Host "  $root"
Write-Host ''
Write-Host 'Please wait...'
Write-Host ''

# ---------------------------------------------------------------------------
# 1. Python
# ---------------------------------------------------------------------------
$python = Get-PythonExe
if ($python) {
    & $python -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  [   ] Existing Python has no pip - bootstrapping...'
        if (-not (Ensure-Pip $python)) { Fail 'pip bootstrap failed for detected Python.' }
        Write-Host '  [ OK ] pip installed'
    }
    Write-Host "  [ OK ] Python detected"
} else {
    $python = Install-PortablePython
    if (-not $python) { Fail 'Python install failed.' }
    Write-Host '  [ OK ] Python ready'
}

# ---------------------------------------------------------------------------
# 2. Node.js (need >= 22 for Claude Code)
# ---------------------------------------------------------------------------
$nodeMajor = Get-NodeMajor
if ($nodeMajor -and $nodeMajor -ge 22) {
    Write-Host "  [ OK ] Node.js detected (v$nodeMajor)"
} else {
    if (-not (Install-PortableNode)) { Fail 'Node.js install failed.' }
    Refresh-ProcessPath
    Write-Host '  [ OK ] Node.js ready'
}

# ---------------------------------------------------------------------------
# 3. Claude Code CLI
# ---------------------------------------------------------------------------
$npmCmd = if (Test-Path "$env:ComSpec") { 'npm.cmd' } else { 'npm' }
$claudeOk = Invoke-Step 'Installing Claude Code CLI (a few minutes)' $npmCmd @('install', '-g', '@anthropic-ai/claude-code@latest') $log -Verify { [bool](& npm ls -g @anthropic-ai/claude-code 2>$null | Select-String 'claude-code@') }
if (-not $claudeOk) { Fail 'Claude Code install failed.' }

# ---------------------------------------------------------------------------
# 4. Cosplay Python dependencies
# ---------------------------------------------------------------------------
$depsOk = Invoke-Step 'Installing Cosplay dependencies' $python @('-m', 'pip', 'install', '--upgrade', '-r', (Join-Path $root 'requirements.txt'), '--no-warn-script-location') $log -Verify { & $python -c "import uvicorn,fastapi,httpx,pydantic,websockets,yaml,dotenv" 2>$null; $LASTEXITCODE -eq 0 }
if (-not $depsOk) { Fail 'Cosplay dependency install failed.' }

# ---------------------------------------------------------------------------
# 5. Configuration
# ---------------------------------------------------------------------------
$env:CCLDUDE_SETUP_NO_LAUNCH = '1'
$cfgOk = Invoke-Step 'Configuring Cosplay' $python @("$root\cclaude_setup.py") $log -Verify {
    (Test-Path (Join-Path $HOME '.cosplay\runtime.json')) -and
    (Test-Path (Join-Path $HOME '.cosplay\providers.json'))
}
if (-not $cfgOk) { Fail 'Cosplay configuration failed.' }

# ---------------------------------------------------------------------------
# 6. Register cclaude on PATH
# ---------------------------------------------------------------------------
Add-ToUserPath @($root)

# ---------------------------------------------------------------------------
# 7. Desktop shortcut (with Cosplay logo if available)
# ---------------------------------------------------------------------------
$shortcutOk = $false
try {
    Add-Type -AssemblyName System.Drawing
    $logo = Join-Path $root 'Cosplay-LOGO.png'
    $icon = Join-Path $root 'cclaude.ico'
    if (Test-Path $logo) {
        $bmp = [System.Drawing.Bitmap]::new($logo)
        try {
            $sq = New-Object System.Drawing.Bitmap 256, 256
            try {
                $g = [System.Drawing.Graphics]::FromImage($sq)
                $g.InterpolationMode = 'HighQualityBicubic'
                $g.SmoothingMode = 'HighQuality'
                $g.DrawImage($bmp, 0, 0, 256, 256)
                $g.Dispose()
                $hIcon = $sq.GetHicon()
                try {
                    $ic = [System.Drawing.Icon]::FromHandle($hIcon)
                    $fs = [IO.File]::Create($icon)
                    try { $ic.Save($fs) } finally { $fs.Dispose() }
                } finally { try { [System.Runtime.InteropServices.Marshal]::DestroyIcon($hIcon) } catch { } }
            } finally { $sq.Dispose() }
        } finally { $bmp.Dispose() }
    }
    $desktop = [Environment]::GetFolderPath('Desktop')
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut((Join-Path $desktop 'cclaude.lnk'))
    $sc.TargetPath = Join-Path $root 'cclaude.cmd'
    $sc.WorkingDirectory = $root
    $sc.Description = 'Cosplay - Launch Claude Code'
    if (Test-Path $icon) { $sc.IconLocation = $icon }
    $sc.Save()
    $shortcutOk = $true
} catch {
    $shortcutOk = $false
}
if ($shortcutOk) { Write-Host '  [ OK ] Desktop shortcut created' }
else             { Write-Host '  [FAIL] Desktop shortcut not created' }

# ---------------------------------------------------------------------------
# 8. Start server
# ---------------------------------------------------------------------------
Write-Host '  [   ] Starting local server...' -NoNewline
$serverOk = $false
$frames = '|', '/', '-', '\'
$fi = 0
for ($i = 0; $i -lt 6; $i++) {
    Write-Host "`r  [ $($frames[$fi % 4]) ] Starting local server..." -NoNewline
    $fi++
    try { if ((Invoke-WebRequest 'http://127.0.0.1:8082/api/runtime' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200) { $serverOk = $true; break } } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $serverOk) {
    try {
        $srvErr = Join-Path $HOME '.cosplay\server.log'
        $srvOut = Join-Path $HOME '.cosplay\server.out.log'
        Start-Process -FilePath $python -ArgumentList @("`"$root\cosplay.py`"", '--no-open') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardError $srvErr -RedirectStandardOutput $srvOut
    } catch {
        Start-Process -FilePath $python -ArgumentList @("`"$root\cosplay.py`"", '--no-open') -WorkingDirectory $root -WindowStyle Hidden
    }
    for ($i = 0; $i -lt 30; $i++) {
        Write-Host "`r  [ $($frames[$fi % 4]) ] Starting local server..." -NoNewline
        $fi++
        try { if ((Invoke-WebRequest 'http://127.0.0.1:8082/api/runtime' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200) { $serverOk = $true; break } } catch { }
        Start-Sleep -Milliseconds 500
    }
}
if ($serverOk) { Write-Host "`r  [ OK ] Local server started" }
else           { Write-Host "`r  [FAIL] Server did not respond" }

Start-Process 'http://127.0.0.1:8082'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Start-Sleep -Milliseconds 500
Clear-Host
Write-Host '------------------------------------------------------------'
Write-Host '============================================================'
Write-Host '                 Cosplay v3.9  | Full Setup'
Write-Host '============================================================'
Write-Host ''
Write-Host '  [ OK ] Python'
Write-Host '  [ OK ] Node.js'
if ($claudeOk) { Write-Host '  [ OK ] Claude Code CLI' }
if ($depsOk)   { Write-Host '  [ OK ] Cosplay dependencies' }
if ($cfgOk)    { Write-Host '  [ OK ] Cosplay configured' }
if ($shortcutOk) { Write-Host '  [ OK ] Desktop shortcut' }
if ($serverOk) { Write-Host '  [ OK ] Local server started' }
else           { Write-Host '  [FAIL] Local server not responding' }
Write-Host ''
Write-Host '------------------------------------------------------------'
Write-Host '          Congrats, Setup Complete !!!'
Write-Host '------------------------------------------------------------'
Write-Host ''
Write-Host '  Admin Dashboard : http://127.0.0.1:8082'
Write-Host ''
Write-Host '  Set API and Enjoy !!!'
Write-Host ''
Write-Host '  Run Anytime by : cclaude'
Write-Host ''
Write-Host '============================================================'
Write-Host ''
Write-Host ''
Write-Host '  Press any key to run cclaude, after setup an API Key !'
Write-Host ''
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
Clear-Host
& "$root\cclaude.cmd"
