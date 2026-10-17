@echo off
rem Double-click to start VoiceGuard. Edit the "rem" lines below to change settings.
call C:\vg\Scripts\activate.bat
set VOICEGUARD_DEMO=
rem set VOICEGUARD_MODEL=sparshsinghal/deepfakeguard-finetuned
rem set "VOICEGUARD_FAKE_LABEL=\breal\b"
rem set VOICEGUARD_T_FLAG=0.65
rem set VOICEGUARD_DEBUG=1
cd /d "%~dp0"
python app.py
pause
