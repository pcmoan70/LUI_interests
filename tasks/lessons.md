# Lessons

- 2026-10-21 SQLite + several scraper processes: never hold a write transaction across a network call
  (fetch first, then write, commit per item). Symptom was "database is locked" and crawls crawling at
  10 s/item even when everything was cached.
- 2026-10-21 Cache-key bug: `Fetcher.get_text(url + "#fragment")` fetches the base URL; never use a
  fetcher call just to probe a cache file, check the cache path directly.
- 2026-10-21 Windows: always run Python with PYTHONUTF8=1; json.load on cp1252 default breaks on
  Norwegian characters.
- 2026-10-21 NVA search: `from=` offset paging returns 400 past 10 000 records; follow
  `nextSearchAfterResults` (search_after cursor) instead of `nextResults`.
- 2026-10-21 Browser pane may be hidden: requestAnimationFrame (and d3 transitions/simulations) do not run,
  and the canvas measures 0×0. Warm up force layouts synchronously with sim.tick() and apply the initial
  zoom transform without a transition; guard canvas sizing with a fallback size.
- 2026-10-21 Regex vocabularies need word boundaries for Norwegian compounds ("danning" matched "utdanning").
- 2026-10-21 Bash heredocs in this environment mangle backslashes; write patch scripts with the Write tool
  and run them with python -I instead of inline heredocs when regexes are involved.
- 2026-10-21 Attribution: embedding similarity alone missed explicitly stated interests (bio said 'kritisk tenkning', talks were title-only). Always keep a lexical channel (keywords in titles/bios) next to embeddings, include talk titles, and audit stated-vs-profiled interests.
