// This file is only used for development: in production, the node server
// index.js is used instead. Both share one proxy definition so that the SSE
// disconnect handling cannot drift between them.
const { createApiProxy } = require("../../server/apiProxy");

const apiProxy = createApiProxy();

module.exports = (app) => {
  // mount `apiProxy` in web server
  app.use("/api", apiProxy);
  app.use("/docs", apiProxy);
  app.use("/openapi.json", apiProxy);
};
