@echo off
rem Weekly (Sunday 07:15): incremental "what's new" update of all sources, full rebuild of derived data, publish.
rem   oslomet.no   no change feed -> staff listing and group pages are re-read; profiles refreshed when older than 90 days
rem   Cristin      modified_since: results and projects changed since the day before the last run (+ fresh listings for new staff)
rem   NVA          modifiedSince: resources changed since the day before the last run
rem   OpenAlex     "updated since" is paid-only -> all DOI batches re-read (~85 requests); works whose citation count
rem                changed are queued and only their citing works are downloaded again (budget 900/run, 1 000/day quota;
rem                a queue that does not fit continues next week)
cd /d C:\Users\wiklund\Documents\ILU_interesser
set PYTHONUTF8=1
set PY=.venv\Scripts\python
set LOG=data\scheduled.log
echo ==== weekly %date% %time% ==== >> %LOG%
%PY% -m lui scrape-oslomet --max-age 90 --fresh list_,group_ >> %LOG% 2>&1
%PY% -m lui scrape-cristin --since auto --fresh persons_lui,results_,projects_oslomet >> %LOG% 2>&1
%PY% -m lui scrape-nva --since auto >> %LOG% 2>&1
%PY% -m lui scrape-openalex --fresh works_batch_ >> %LOG% 2>&1
%PY% -m lui scrape-pdf >> %LOG% 2>&1
%PY% -m lui scrape-openalex-cites >> %LOG% 2>&1
%PY% -m lui identity >> %LOG% 2>&1
%PY% -m lui embed >> %LOG% 2>&1
%PY% -m lui tag >> %LOG% 2>&1
%PY% -m lui externals >> %LOG% 2>&1
%PY% -m lui build-edges >> %LOG% 2>&1
%PY% -m lui build-matrices >> %LOG% 2>&1
%PY% -m lui build-collab >> %LOG% 2>&1
%PY% -m lui export-web >> %LOG% 2>&1
%PY% -m lui export-graph >> %LOG% 2>&1
%PY% -m lui verify >> %LOG% 2>&1
git add web\data >> %LOG% 2>&1
git -c core.quotepath=off commit -q -m "Weekly update: new publications, staff and citation data" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" >> %LOG% 2>&1
git push >> %LOG% 2>&1
echo ==== weekly done %date% %time% ==== >> %LOG%
