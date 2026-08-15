// Mock for the `qr-scanner` package, wired in via `moduleNameMapper` in
// package.json. The real module drives a Worker and a canvas to decode
// images, neither of which jsdom provides, so src/QRParser.js gets this
// stand-in instead whenever it imports "qr-scanner".
//
// Usage in a test:
//   import { setNextScanResult } from "../testMocks/qrScanner";
//   setNextScanResult({ data: "some-qr-payload" }); // next scanImage() resolves with this
//   setNextScanResult(null); // back to the default: scanImage() rejects ("no QR code found")

const createQrEngine = jest.fn(() => Promise.resolve({}));

// null (the default) means "no QR code found", matching QRParser's real
// behaviour when scanImage rejects.
let nextResult = null;

const scanImage = jest.fn(() =>
  nextResult
    ? Promise.resolve(nextResult)
    : Promise.reject(new Error("No QR code found")),
);

export function setNextScanResult(result) {
  nextResult = result;
}

// Called from setupTests.js before every test. nextResult is a plain closure
// variable rather than jest mock state, so jest.clearAllMocks() alone (which
// only clears call history, not this) won't reset it between tests.
export function __resetQrScannerMock() {
  nextResult = null;
}

const QrScanner = { createQrEngine, scanImage };

export default QrScanner;
