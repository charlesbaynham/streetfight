import { createRef } from "react";
import { render } from "@testing-library/react";
import { MyWebcam } from "./MyWebcam";

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
