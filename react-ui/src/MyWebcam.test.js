import { createRef } from "react";
import { render, waitFor } from "@testing-library/react";
import { MyWebcam } from "./MyWebcam";
import prose from "./prose";
import { clearRefusal, getRefusal } from "./refusalStore";

jest.mock("./utils", () => ({ watchCompassHeading: () => () => {} }));

beforeEach(() => {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: jest.fn(() => new Promise(() => {})) },
  });
  HTMLMediaElement.prototype.play = jest.fn();
});

test("capture returns null before the camera has delivered a frame", () => {
  const toDataURL = jest.fn(() => "data:,");
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({ drawImage() {} }));
  HTMLCanvasElement.prototype.toDataURL = toDataURL;
  const ref = createRef();

  render(<MyWebcam ref={ref} trigger={0} />);

  expect(ref.current.capture()).toBeNull();
  expect(toDataURL).not.toHaveBeenCalled();
});

// A shot the server turns down used to be indistinguishable from one that
// worked: the response was parsed as JSON and thrown away, so a 403 - no
// ammo, dead, or inside the fire cooldown (M1.1) - looked to the player like
// the app had eaten the shot (docs/r9_walkthrough/A4.md).
describe("a refused shot", () => {
  const frame = "data:image/jpeg;base64,AAAA";

  function renderWithAFrame() {
    HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
      drawImage() {},
    }));
    HTMLCanvasElement.prototype.toDataURL = jest.fn(() => frame);
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", {
      configurable: true,
      value: 640,
    });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", {
      configurable: true,
      value: 480,
    });

    // trigger goes 0 -> 1 to fire a capture
    const { rerender } = render(<MyWebcam trigger={0} />);
    rerender(<MyWebcam trigger={1} />);
  }

  beforeEach(() => {
    clearRefusal();
  });

  test("publishes the server's reason", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        json: () =>
          Promise.resolve({
            detail: "Still reloading - 12.3 s of cooldown left",
          }),
      }),
    );

    renderWithAFrame();
    await waitFor(() => expect(getRefusal()).not.toBeNull());

    expect(getRefusal().message).toBe(
      prose.fireButton.shotRefused("Still reloading - 12.3 s of cooldown left"),
    );
  });

  test("publishes a refusal even when the body says nothing useful", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        json: () => Promise.reject(new Error("no body")),
      }),
    );

    renderWithAFrame();
    await waitFor(() => expect(getRefusal()).not.toBeNull());

    expect(getRefusal().message).toBe(prose.fireButton.shotRefusedUnknown);
  });

  test("a shot that lands publishes nothing", async () => {
    const json = jest.fn(() => Promise.resolve({}));
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json }));

    renderWithAFrame();
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());

    expect(getRefusal()).toBeNull();
  });
});
