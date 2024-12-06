// This file is only used for development: in production, the node server
// index.js is used instead
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");

// create the proxy (without context)
const apiProxy = createProxyMiddleware({
  target: "http://127.0.0.1:8000", // target host
  changeOrigin: false,
  ws: false,
});

module.exports = (app) => {
  // mount `apiProxy` in web server
  app.use("/api", apiProxy);
  app.use("/docs", apiProxy);
  app.use("/openapi.json", apiProxy);
};
