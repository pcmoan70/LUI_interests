@echo off
rem Daily: fetch citing works within the OpenAlex quota, rebuild collaboration data, export and publish.
cd /d C:\Users\wiklund\Documents\ILU_interesser
set PYTHONUTF8=1
echo ==== %date% %time% ==== >> data\scheduled.log
.venv\Scripts\python -m lui scrape-openalex-cites >> data\scheduled.log 2>&1
.venv\Scripts\python -m lui build-collab >> data\scheduled.log 2>&1
.venv\Scripts\python -m lui export-web >> data\scheduled.log 2>&1
git add web\data >> data\scheduled.log 2>&1
git -c core.quotepath=off commit -q -m "Scheduled update: citation data" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" >> data\scheduled.log 2>&1
git push >> data\scheduled.log 2>&1
