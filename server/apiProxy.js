// The one place /api is proxied to the FastAPI backend.
//
// Both node servers here need it - the CRA dev server
// (react-ui/src/setupProxy.js) and the production server (index.js) - and both
// carry the SSE streams, so the disconnect handling below lives here rather
// than in two copies that can drift apart. The Caddy deployments
// (Caddyfile, nix/streetfight.nix) reverse-proxy the backend themselves and
// never load this.
const { createProxyMiddleware } = require("http-proxy-middleware");

const BACKEND = "http://127.0.0.1:8000";

function createApiProxy(options = {}) {
  return createProxyMiddleware({
    target: BACKEND,
    changeOrigin: false, // needed for virtual hosted sites
    ws: false, // don't proxy websockets
    ...options,

    onProxyReq: (proxyReq, req, res) => {
      // node-http-proxy only tears the upstream request down when the incoming
      // request emits "aborted", and a GET that arrived complete never emits
      // it - closing the browser tab fires "close" on the response instead. So
      // without this, every closed SSE tab leaves the backend streaming
      // keepalives into a socket nobody reads, forever: its generator stays
      // parked at a yield that always succeeds, so the cleanup in
      // backend/sse_event_streams.py that cancels the producer tasks never
      // runs. Caddy gets this right, which is why only the node path leaked.
      res.on("close", () => {
        if (!res.writableFinished) {
          proxyReq.destroy();
        }
      });
    },

    onError: (err, req, res) => {
      // Destroying the upstream request above surfaces here as a reset. That
      // is the expected end of a stream whose client has gone, not a fault.
      if (res.writableEnded || res.headersSent) {
        res.destroy();
        return;
      }
      console.error(`Proxy error for ${req.url}: ${err.message}`);
      res.writeHead(502).end("Bad gateway");
    },
  });
}

module.exports = { createApiProxy };
