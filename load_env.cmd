@echo off
rem Loads KEY=VALUE lines from .env (next to this file) into the CURRENT cmd session.
rem Lines starting with # are skipped. Run once per new cmd window: load_env
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do set "%%a=%%b"
echo Loaded .env into this session.