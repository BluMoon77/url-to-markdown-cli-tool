# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm install                 # also downloads a Chromium build via puppeteer
npm test                    # jest (all suites)
npx jest tests/table-conversion.test.js          # single file
npx jest -t "should convert basic 3x3 table"     # single test by name
npx jest --coverage         # coverage (src/index.js is excluded by jest.config.js)

node src/index.js <url> [options]   # run the CLI locally (same as `npm start -- <url>`)
npm install -g .                    # install the `url-to-md` binary from source
```

There is no linter or build step. Node >= 18 and a Chrome/Chromium binary are required.

## Architecture

Three modules, one linear pipeline: `src/index.js` (CLI) → `src/lib/pageFetcher.js` (fetch) → `src/lib/markdownProcessor.js` (convert).

**`src/index.js`** — Commander setup, all input validation (URL parsing, wait >= 0, viewport bounds, mutually exclusive viewport presets), and *option translation*. This is where CLI flags become library options, and the mapping is not one-to-one:

- Commander's `--no-x` flags mean `options.images`/`links`/`gifImages`/`svgImages` are `true` unless the flag is passed. `index.js` inverts them into `keepImages`, `keepWebpageLinks`, `removeGifImage`, `removeSvgImage`.
- `--clean-content` has no counterpart in the processor; `index.js` expands it into a fixed tag list (`nav footer aside script style header noscript canvas`) appended to `removeTags`.
- Viewport presets (`--mobile`/`--tablet`/`--desktop`) overwrite `viewportWidth`/`viewportHeight` before validation. Defaults are mobile-first (375x667), so pages render as mobile unless a preset or explicit size is given.

**`src/lib/pageFetcher.js`** — `getPageSource()` launches Puppeteer, sets viewport + a desktop Chrome user agent, navigates with `waitUntil: 'domcontentloaded'` (30s timeout), sleeps `wait` seconds, then waits for `readyState === 'complete'` but *swallows that timeout* and returns partial content rather than failing. It re-validates viewport bounds independently of the CLI. `--disable-web-security` is the only Chrome flag added conditionally.

**`src/lib/markdownProcessor.js`** — `getProcessedMarkdown()` is the whole conversion, and step order matters:

1. `filterToIncludeTags()` — clones every element matching `includeTags` into a fresh `<body>`. Nested matches are cloned independently, so including a tag that nests inside another included tag duplicates content. No matches logs a warning and returns an empty document; an internal throw falls back to the unfiltered document.
2. Tag removal — `script`/`style` plus `removeTags`, then **filtered so anything in `includeTags` is never removed** (include wins over remove).
3. `addSpacingBetweenElements()` — injects newlines/spaces into the DOM between adjacent block/inline elements so Turndown doesn't concatenate text.
4. Image handling — drop by extension (`.svg`, `.gif`) or entirely, otherwise resolve `src` against `baseUrl` and replace the `<img>` with literal `![alt](url)` text.
5. Link handling — unwrap `<a>` to its text, or rewrite `href` to absolute.
6. Turndown with custom rules, then `postProcessMarkdown()`.

### Things that bite

- **Library defaults differ from CLI defaults.** `getProcessedMarkdown` defaults `removeSvgImage`/`removeGifImage` to `true`, but the CLI passes `false` unless `--no-svg-images`/`--no-gif-images` is given. Tests calling the processor directly therefore strip SVG/GIF by default; the CLI does not.
- **Table conversion is custom, not Turndown's.** When `preserveTableStructure` is true (default in the processor, not exposed as a CLI flag) four rules replace `table`/`tr`/`th`/`td`/`caption`. The `table` rule owns the whole render — it walks `querySelectorAll('tr')` itself and calls `turndownService.turndown()` recursively on each cell's `innerHTML`, collapsing newlines and escaping pipes. Colspan/rowspan are not expanded; the header separator row is emitted only when the first row contains `<th>`.
- **`postProcessMarkdown()` applies heuristic regex text repairs** (space after `.!?` before a capital, `20%Increased` → `20% Increased`, `Logo|Inc|Corp|Ltd|LLC` suffixes) plus blank-line and header/list spacing normalization. These regexes are global text surgery — changing one tends to move many test assertions.
- **The version string is duplicated**: `package.json` and the hardcoded `.version('1.1.0')` in `src/index.js`. Bump both.
- `package.json` `files` whitelists what ships to npm (`src/index.js`, `src/lib/`, `README.md`); new source directories must be added there.

## Tests

- `tests/include-tags.test.js` and `tests/table-conversion.test.js` call `getProcessedMarkdown()` directly against HTML fixtures in `tests/fixtures/{include-tags,tables}/` — no browser, no network. Add new conversion behavior here with a fixture.
- `tests/cli.test.js` spawns the real CLI via `child_process.spawn` and **several tests hit the network** (`httpbin.org`, `example.com`) with 10s timeouts; they assert on argument-parsing/error output rather than fetched content, so they pass offline but run slowly.
- Assertions are mostly `toContain` on substrings rather than exact-output snapshots, deliberately tolerating whitespace differences.

## Related files

`AGENTS.md` is a short orientation file covering the same structure for other agents — keep it consistent when the layout or tech stack changes.
