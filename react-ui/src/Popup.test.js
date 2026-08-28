import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import Popup from "./Popup";

// jsdom does no layout, so the scroll geometry the hint keys off has to be
// supplied by hand
function setGeometry({ scrollHeight, clientHeight, scrollTop }) {
  const container = document.querySelector(".innerContainer");
  for (const [property, value] of Object.entries({
    scrollHeight,
    clientHeight,
    scrollTop,
  }))
    Object.defineProperty(container, property, {
      configurable: true,
      value,
    });
  return container;
}

function renderPopup() {
  render(
    <Popup visible={true} setVisible={() => {}}>
      <p>Some content</p>
    </Popup>,
  );
}

const scrollHint = () => screen.queryByLabelText("Scroll down for more");

test("no hint when everything fits in the box", () => {
  renderPopup();
  const container = setGeometry({
    scrollHeight: 200,
    clientHeight: 200,
    scrollTop: 0,
  });
  fireEvent.scroll(container);

  expect(scrollHint()).not.toBeInTheDocument();
});

test("hint appears while there is content below the fold", () => {
  renderPopup();
  const container = setGeometry({
    scrollHeight: 500,
    clientHeight: 200,
    scrollTop: 0,
  });
  fireEvent.scroll(container);

  expect(scrollHint()).toBeInTheDocument();
});

test("hint goes away once the bottom is in view", () => {
  renderPopup();
  let container = setGeometry({
    scrollHeight: 500,
    clientHeight: 200,
    scrollTop: 0,
  });
  fireEvent.scroll(container);
  expect(scrollHint()).toBeInTheDocument();

  container = setGeometry({
    scrollHeight: 500,
    clientHeight: 200,
    scrollTop: 300,
  });
  fireEvent.scroll(container);

  expect(scrollHint()).not.toBeInTheDocument();
});

test("tapping the hint scrolls to the bottom of the box", () => {
  renderPopup();
  const container = setGeometry({
    scrollHeight: 500,
    clientHeight: 200,
    scrollTop: 0,
  });
  container.scrollTo = jest.fn();
  fireEvent.scroll(container);

  fireEvent.click(scrollHint());

  expect(container.scrollTo).toHaveBeenCalledWith({
    top: 300,
    behavior: "smooth",
  });
});
