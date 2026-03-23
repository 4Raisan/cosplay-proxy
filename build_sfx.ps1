# Builds a minimal, distributable Cosplay package:
#   - Cosplay-Setup.cmd        self-extracting installer (1 click, no icon)
#   - Cosplay-Full-Setup.exe   self-extracting installer (logo icon, built with
#                              the .NET Framework csc that ships with Windows)
#
# Both embed the same package and, when run, extract to %LocalAppData%\Cosplay
# and run setup.ps1.
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\build_sfx.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stage = Join-Path $env:TEMP 'cosplay-pkg-stage'
$zip   = Join-Path $env:TEMP 'cosplay-pkg.zip'
$outCmd = Join-Path $root 'Cosplay-Setup.cmd'

# ---- minimum runtime files (relative to repo root) -----------------------
$files = @(
    'cclaude-setup.bat',
    'setup.ps1',
    'uninstall.cmd',
    'uninstall.ps1',
    'Cosplay-LOGO.png',
    'cclaude_setup.py',
    'cclaude.py',
    'cosplay.py',
    'server.py',
    'daemon.py',
    'requirements.txt',
    'README.md',
    'Fixer.md',
    'proxy',
    'config',
    'providers',
    'api',
    'static'
)

Write-Host '[1/4] Staging minimal files...'
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($f in $files) {
    $src = Join-Path $root $f
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src (Join-Path $stage $f)
    } else {
        Write-Warning "Missing: $f"
    }
}

Write-Host '[2/4] Stripping caches...'
Get-ChildItem -Path $stage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $stage -Recurse -File -Include '*.pyc' -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host '[3/4] Compressing...'
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal

$bytes = [IO.File]::ReadAllBytes($zip)
$b64 = [Convert]::ToBase64String($bytes)

Write-Host '[4/4] Writing self-extracting launcher...'
$header = @'
@echo off
setlocal EnableExtensions
title Cosplay + Claude Code - One-Click Setup
set "DEST=%LocalAppData%\Cosplay"
echo  Extracting package...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lines=Get-Content '%~f0';$b64=$lines[$lines.Count-1].Trim();[IO.File]::WriteAllBytes('%TEMP%\cosplay-pkg.zip',[Convert]::FromBase64String($b64));if(-not (Test-Path '%DEST%')){New-Item -ItemType Directory -Force '%DEST%' | Out-Null};Expand-Archive -Force '%TEMP%\cosplay-pkg.zip' '%DEST%';Remove-Item '%TEMP%\cosplay-pkg.zip'"
if errorlevel 1 goto :extractfail
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\setup.ps1"
exit /b 0

:extractfail
echo  [ERROR] Failed to extract package.
pause
exit /b 1
'@

# header with CRLF + no BOM, then the base64 as the final line (no trailing NL)
$enc = New-Object System.Text.UTF8Encoding($false)
$headerText = ($header -replace "`r?`n", "`r`n") + "`r`n"
$outCmdTmp = "$outCmd.tmp"
[System.IO.File]::WriteAllText($outCmdTmp, $headerText + $b64, $enc)
$moved = $false
for ($i = 0; $i -lt 5 -and -not $moved; $i++) {
    try { Move-Item -Force $outCmdTmp $outCmd; $moved = $true }
    catch { Start-Sleep -Milliseconds 400 }
}
if (-not $moved) {
    Write-Warning "Could not update $outCmd (file in use) - leaving previous build."
}

Write-Host '[5/5] Building Cosplay-Full-Setup.exe...'

# ---- 5a. Convert logo -> .ico for the EXE icon ----------------------------
Add-Type -AssemblyName System.Drawing
$logo = Join-Path $root 'Cosplay-LOGO.png'
$ico  = Join-Path $env:TEMP 'cosplay-sfx.ico'
if (-not (Test-Path $logo)) { throw 'Cosplay-LOGO.png not found - cannot build EXE with icon.' }
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
            $fs = [IO.File]::Create($ico)
            try { $ic.Save($fs) } finally { $fs.Dispose() }
        } finally { try { [System.Runtime.InteropServices.Marshal]::DestroyIcon($hIcon) } catch { } }
    } finally { $sq.Dispose() }
} finally { $bmp.Dispose() }

# ---- 5b. C# self-extracting stub -----------------------------------------
$stubCs  = Join-Path $env:TEMP 'cosplay-sfx-stub.cs'
$stubExe = Join-Path $env:TEMP 'cosplay-sfx-stub.exe'
$outExe  = Join-Path $root 'Cosplay-Full-Setup.exe'

$stubSource = @'
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;

class Program
{
    static void Fail(string msg)
    {
        Console.WriteLine(msg);
        Console.WriteLine("Press any key to exit...");
        Console.ReadKey();
        Environment.Exit(1);
    }

    static void Main(string[] args)
    {
        string self = Assembly.GetExecutingAssembly().Location;
        byte[] data;
        try { data = File.ReadAllBytes(self); }
        catch (Exception ex) { Fail("Cannot read installer: " + ex.Message); return; }

        const string magic = "COSPLAYSFX";
        int n = data.Length;
        if (n < magic.Length + 8 || Encoding.ASCII.GetString(data, n - magic.Length - 8, magic.Length) != magic)
            Fail("Corrupt installer package (missing payload).");

        long zipLen = BitConverter.ToInt64(data, n - 8);
        int zipStart = n - magic.Length - 8 - (int)zipLen;
        if (zipStart < 0 || zipLen > data.Length)
            Fail("Corrupt installer package (bad payload length).");

        string tmp = Path.Combine(Path.GetTempPath(), "cosplay-pkg-" + Guid.NewGuid().ToString("N") + ".zip");
        try
        {
            using (FileStream fs = File.Create(tmp)) { fs.Write(data, zipStart, (int)zipLen); }
        }
        catch (Exception ex) { Fail("Cannot write temp package: " + ex.Message); return; }

        string dest = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Cosplay");
        try
        {
            if (Directory.Exists(dest)) Directory.Delete(dest, true);
            Directory.CreateDirectory(dest);
            ZipFile.ExtractToDirectory(tmp, dest);
        }
        catch (Exception ex)
        {
            Fail("Extract failed: " + ex.Message);
            return;
        }
        finally { try { File.Delete(tmp); } catch { } }

        string ps = Path.Combine(dest, "setup.ps1");
        if (!File.Exists(ps)) Fail("setup.ps1 missing after extraction.");

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo("powershell.exe",
                "-NoProfile -ExecutionPolicy Bypass -File \"" + ps + "\"");
            psi.UseShellExecute = false;
            Process p = Process.Start(psi);
            p.WaitForExit();
            Environment.Exit(p.ExitCode);
        }
        catch (Exception ex)
        {
            Fail("Cannot launch setup: " + ex.Message);
        }
    }
}
'@
[System.IO.File]::WriteAllText($stubCs, $stubSource, $enc)

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path $csc)) { throw 'csc.exe not found - cannot build EXE.' }

& $csc -nologo -target:exe -win32icon:"$ico" -out:"$stubExe" `
    -r:System.IO.Compression.dll -r:System.IO.Compression.FileSystem.dll $stubCs | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $stubExe)) { throw 'csc.exe failed to compile the stub.' }

# ---- 5c. Append zip payload + footer marker ------------------------------
$zipBytes = [IO.File]::ReadAllBytes($zip)
$exeBytes = [IO.File]::ReadAllBytes($stubExe)
$footer = [byte[]]([Text.Encoding]::ASCII.GetBytes('COSPLAYSFX') + [BitConverter]::GetBytes([long]$zipBytes.Length))
$outBytes = New-Object byte[] ($exeBytes.Length + $zipBytes.Length + $footer.Length)
[Buffer]::BlockCopy($exeBytes, 0, $outBytes, 0, $exeBytes.Length)
[Buffer]::BlockCopy($zipBytes, 0, $outBytes, $exeBytes.Length, $zipBytes.Length)
[Buffer]::BlockCopy($footer, 0, $outBytes, $exeBytes.Length + $zipBytes.Length, $footer.Length)
[IO.File]::WriteAllBytes($outExe, $outBytes)

Remove-Item -Force $stubCs, $stubExe, $ico -ErrorAction SilentlyContinue

# clean up stage
Remove-Item -Recurse -Force $stage
Remove-Item -Force $zip

Write-Host ''
Write-Host 'Done.'
Write-Host "  SFX CMD : $outCmd   ($([math]::Round((Get-Item $outCmd).Length/1kb)) KB)"
Write-Host "  SFX EXE : $outExe   ($([math]::Round((Get-Item $outExe).Length/1kb)) KB)"
