# AGENTS.md

Purpose
- Node.js CLI that converts web pages into clean, LLM-friendly markdown.
- Fetches pages via Puppeteer, strips noise, and converts HTML to markdown.
- No external APIs or keys required.

Structure
- `src/index.js`: CLI entry point and option parsing.
- `src/lib/pageFetcher.js`: Puppeteer fetching.
- `src/lib/markdownProcessor.js`: HTML to markdown conversion.
- `gui/`: GTK4/libadwaita desktop front-end (Python) that shells out to the CLI.
- `tests/`: Jest tests with fixtures in `tests/fixtures/`, served over a local
  HTTP server (`tests/helpers/server.js`) - no network required.

Tech
- Node.js >= 18.
- Core deps: puppeteer, cheerio, turndown, commander.
- GUI deps: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1.
- Tests: jest (`npm test`).
