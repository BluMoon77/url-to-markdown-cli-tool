/**
 * Local HTTP server for CLI tests.
 *
 * The CLI spawns a real browser, so its tests need a real URL to fetch. Serving
 * fixtures from 127.0.0.1 keeps those tests deterministic and offline, instead
 * of depending on public endpoints that go down or change their markup.
 */

const http = require('http');

/** Mirrors the shape of httpbin.org/html, which these tests originally used. */
const HTML_PAGE = `<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <nav><a href="/">Home</a> <a href="/about">About</a></nav>
  <h1>Herman Melville - Moby-Dick</h1>
  <main>
    <article>
      <h2>Chapter 1</h2>
      <p>Call me Ishmael. Some years ago - never mind how long precisely -
      having little or no money in my purse, I thought I would sail about a
      little and see the watery part of the world.</p>
    </article>
    <section>
      <p>It is a way I have of driving off the spleen.</p>
    </section>
  </main>
  <footer><p>Public domain text.</p></footer>
</body>
</html>`;

/**
 * Start a fixture server on an ephemeral port.
 *
 * Routes:
 *   /html         - the page above
 *   /delay/:secs  - the same page, sent after a delay (for timeout tests)
 *   anything else - 404
 *
 * @returns {Promise<{url: string, close: () => Promise<void>}>} Base URL (no
 *   trailing slash) and a shutdown function.
 */
function startServer() {
    const pending = new Set();

    const server = http.createServer((req, res) => {
        const delayMatch = req.url.match(/^\/delay\/(\d+(?:\.\d+)?)/);

        if (delayMatch) {
            const timer = setTimeout(() => {
                pending.delete(timer);
                res.writeHead(200, { 'Content-Type': 'text/html' });
                res.end(HTML_PAGE);
            }, parseFloat(delayMatch[1]) * 1000);
            pending.add(timer);
            return;
        }

        if (req.url.startsWith('/html')) {
            res.writeHead(200, { 'Content-Type': 'text/html' });
            res.end(HTML_PAGE);
            return;
        }

        res.writeHead(404, { 'Content-Type': 'text/html' });
        res.end('<!DOCTYPE html><html><body><h1>Not Found</h1></body></html>');
    });

    // Browsers keep connections alive; without this the server won't close promptly.
    server.keepAliveTimeout = 100;

    return new Promise((resolve, reject) => {
        server.on('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const { port } = server.address();
            resolve({
                url: `http://127.0.0.1:${port}`,
                close: () => new Promise((done) => {
                    // Cancel in-flight /delay responses so close() isn't blocked.
                    pending.forEach(clearTimeout);
                    pending.clear();
                    server.closeAllConnections?.();
                    server.close(() => done());
                })
            });
        });
    });
}

module.exports = { startServer, HTML_PAGE };
