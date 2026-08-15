// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import "@testing-library/jest-dom";

import { resetTestEnvironment } from "./testUtils";
import { __resetQrScannerMock } from "./testMocks/qrScanner";

// Every test file in this suite gets these global stubs reinstalled fresh
// before each test - see testUtils.js for what each one does. Individual
// tests can still override behaviour (e.g. installFetchMock with a route
// table, setPermission) after this runs.
beforeEach(() => {
  resetTestEnvironment();
  __resetQrScannerMock();
});

// The app logs a lot (console.log/console.debug) as part of normal
// operation - silence that noise but leave console.error/console.warn
// visible so real React warnings (act(), prop-types, etc.) still surface.
beforeEach(() => {
  jest.spyOn(console, "log").mockImplementation(() => {});
  jest.spyOn(console, "debug").mockImplementation(() => {});
});
