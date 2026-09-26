@echo off
title e-Nabiz AI Automated Test Suite
echo =====================================================
echo    e-Nabiz AI -- Running Pytest Automated Tests
echo =====================================================
".venv\Scripts\python.exe" -m pytest tests -v
pause
