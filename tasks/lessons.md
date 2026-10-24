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
- 2026-10-22 OpenAlex now enforces a daily free credit limit (x-ratelimit-limit: 1000 requests/day, 429 with retry-after ~15 h when exhausted). Large citation crawls must be spread over days or use a paid API key; the fetcher honours Retry-After.
- 2026-10-24 Patch scripts that insert a new function "before def X" must check for decorators: inserting between
  `@contextmanager` and `def run_log` silently re-targeted the decorator and broke every stage. Anchor on the
  decorator line (or insert after the function) and run one stage before trusting a compile-only check.
- 2026-10-24 Change feeds: Cristin (`modified_since`) and NVA (`modifiedSince`) support incremental fetches;
  OpenAlex `from_updated_date` is paid-only, so diff on `cited_by_count` instead. Windows Task Scheduler: a trigger
  created with `-At` right before a DST switch got an offset-bearing StartBoundary and shifted by an hour; set a
  plain local StartBoundary (`YYYY-MM-DDTHH:MM:SS`).
