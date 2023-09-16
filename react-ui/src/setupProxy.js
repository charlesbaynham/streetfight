// This file is only used for development: in production, the node server
// index.js is used instead
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');

const PORT = process.env.PORT || 3000;

// create the proxy (without context)
const apiProxy = createProxyMiddleware({
  target: 'http://127.0.0.1:8000', // target host
  changeOrigin: true,
  ws: true,
});

// // create the proxy (without context)
// const wsProxy = createProxyMiddleware({
//   target: 'http://127.0.0.1:8000/ws',
//   changeOrigin: true,
//   ws: true,
// });

const socketProxy = createProxyMiddleware({
  target: 'http://127.0.0.1:8000/ws',
  ws: true,
});

module.exports = app => {
  // mount `apiProxy` in web server
  // app.use('/api/ws', wsProxy);
  // app.use('/myws', socketProxy);
  app.use('/', apiProxy);
  // app.use('/docs', apiProxy);
  // app.use('/openapi.json', apiProxy);
}
