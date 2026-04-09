# Cosplay — SFX Packaging

Cosplay ships as a **single self-extracting file** for clean PCs.

- `Cosplay-Setup.cmd` — a batch header whose final line is the base64 of the whole package; double-click extracts to `%LocalAppData%\Cosplay` and runs `setup.ps1`.
- `Cosplay-Full-Setup.exe` — same package with the Cosplay logo as its icon.
- `build_sfx.ps1` regenerates both after any fix (`Cosplay-Fixer-Log`).
- Recommended clean-room test: run the SFX in a fresh Windows Sandbox and confirm the `Congrats` footer with `GET /api/runtime` → 200.

#cosplay #packaging
