import { render, screen, waitFor, act } from "@testing-library/react";

import QRParser from "./QRParser";
import QrScannerMock, { setNextScanResult } from "./testMocks/qrScanner";
import { getPlaySpy } from "./testMocks/useSound";
import { installFetchMock, getAPICalls, getLastAPICall } from "./testUtils";

// BlankScreen's flash is a framer-motion animation; swap it for a plain marker
// so the flash/color it was asked to show can be read straight off the DOM.
jest.mock("./BlankScreen", () => (props) => (
  <div
    data-testid="blank-screen"
    data-appear={String(props.appear)}
    data-color={props.color}
  />
));

// waitFor drives jest's fake timers itself (see dom-testing-library's
// jestFakeTimersAreEnabled branch), advancing them in small steps until the
// assertion passes or this timeout's worth of *virtual* time has elapsed.
// QRParser's scan loop only ticks once a second, so the default 1000ms
// budget is too tight - give every wait here a lot of headroom instead.
const WAIT = { timeout: 8000 };

function makeWebcamRef(captureImpl = () => "data:image/jpeg;base64,dummy") {
  return { current: { capture: jest.fn(captureImpl) } };
}

function setDocumentHidden(hidden) {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
}

afterEach(() => {
  jest.useRealTimers();
  setDocumentHidden(false);
});

// capture() (in QRParser.js) lazily builds its QR-decoding engine on the very
// first call, module-scope, across this whole file - see the "gotcha" note in
// testUtils.js. Rather than fight that with jest.resetModules() (which breaks
// React's hook dispatch when the freshly-required component ends up on a
// different "react" module instance than the one @testing-library/react is
// bound to), warm the engine up once here on a throwaway instance. Every real
// test below then sees a warm engine, so its very first tick is a real scan
// attempt.
beforeAll(async () => {
  jest.useFakeTimers();
  const ref = makeWebcamRef();
  const { unmount } = render(<QRParser webcamRef={ref} />);
  await waitFor(() => expect(QrScannerMock.scanImage).toHaveBeenCalled(), WAIT);
  unmount();
  jest.useRealTimers();
});

test("a successful scan POSTs collect_item with the scanned data", async () => {
  installFetchMock({ collect_item: {} });
  setNextScanResult({ data: "loot-42" });
  jest.useFakeTimers();
  render(<QRParser webcamRef={makeWebcamRef()} />);

  await waitFor(
    () => expect(getLastAPICall("collect_item")).toBeDefined(),
    WAIT,
  );
  const call = getLastAPICall("collect_item");
  expect(call.method).toBe("POST");
  expect(call.body).toEqual({ data: "loot-42" });
});

test("the same scan data within 5s is not resubmitted; after 5s it is", async () => {
  installFetchMock({ collect_item: {} });
  setNextScanResult({ data: "dup-data" });
  jest.useFakeTimers();
  render(<QRParser webcamRef={makeWebcamRef()} />);

  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(1), WAIT);

  // Still well within the 5s dedup window - further ticks scanning the same
  // data must not resubmit.
  await act(async () => {
    jest.advanceTimersByTime(3000);
  });
  expect(getAPICalls("collect_item").length).toBe(1);

  // Past 5s since the original submission - the same data is fair game again.
  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(2), WAIT);
});

test("different data scanned back to back is always submitted", async () => {
  installFetchMock({ collect_item: {} });
  jest.useFakeTimers();

  setNextScanResult({ data: "item-A" });
  render(<QRParser webcamRef={makeWebcamRef()} />);
  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(1), WAIT);

  setNextScanResult({ data: "item-B" });
  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(2), WAIT);

  setNextScanResult({ data: "item-C" });
  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(3), WAIT);

  expect(getAPICalls("collect_item").map((c) => c.body)).toEqual([
    { data: "item-A" },
    { data: "item-B" },
    { data: "item-C" },
  ]);
});

test("a 403 response flashes the screen red and plays the error sound", async () => {
  installFetchMock({ collect_item: { status: 403, body: {} } });
  setNextScanResult({ data: "forbidden-item" });
  jest.useFakeTimers();
  render(<QRParser webcamRef={makeWebcamRef()} />);

  await waitFor(
    () => expect(getLastAPICall("collect_item")).toBeDefined(),
    WAIT,
  );
  await waitFor(
    () =>
      expect(screen.getByTestId("blank-screen").dataset.appear).toBe("true"),
    WAIT,
  );
  expect(screen.getByTestId("blank-screen").dataset.color).toBe("red");
  expect(getPlaySpy()).toHaveBeenCalled();
});

test("a 404 response is ignored - no flash, no sound (the scanner misfires)", async () => {
  installFetchMock({ collect_item: { status: 404, body: {} } });
  setNextScanResult({ data: "misfire-item" });
  jest.useFakeTimers();
  render(<QRParser webcamRef={makeWebcamRef()} />);

  await waitFor(
    () => expect(getLastAPICall("collect_item")).toBeDefined(),
    WAIT,
  );
  await act(async () => {}); // flush the response handling itself
  expect(screen.getByTestId("blank-screen").dataset.appear).toBe("false");
  expect(getPlaySpy()).not.toHaveBeenCalled();
});

test("a 200 response produces neither a flash nor a sound", async () => {
  installFetchMock({ collect_item: {} });
  setNextScanResult({ data: "ok-item" });
  jest.useFakeTimers();
  render(<QRParser webcamRef={makeWebcamRef()} />);

  await waitFor(
    () => expect(getLastAPICall("collect_item")).toBeDefined(),
    WAIT,
  );
  await act(async () => {});
  expect(screen.getByTestId("blank-screen").dataset.appear).toBe("false");
  expect(getPlaySpy()).not.toHaveBeenCalled();
});

test("does not capture while document.hidden is true, and resumes once visible again", async () => {
  installFetchMock({ collect_item: {} });
  setNextScanResult({ data: "hidden-item" });
  setDocumentHidden(true);
  const ref = makeWebcamRef();
  jest.useFakeTimers();
  render(<QRParser webcamRef={ref} />);

  // Give it plenty of time to have scanned by now, were it not hidden.
  await act(async () => {
    jest.advanceTimersByTime(3000);
  });
  expect(ref.current.capture).not.toHaveBeenCalled();
  expect(getAPICalls("collect_item").length).toBe(0);

  setDocumentHidden(false);
  await act(async () => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

  await waitFor(() => expect(getAPICalls("collect_item").length).toBe(1), WAIT);
});
