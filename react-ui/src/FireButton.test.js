import { render, screen, fireEvent, act } from "@testing-library/react";

import FireButton from "./FireButton";
import { makeUser } from "./testUtils";
import { getPlaySpy } from "./testMocks/useSound";

import fireButtonImg from "./images/firebutton.svg";
import fireButtonImgNoAmmo from "./images/firebutton_no_ammo.svg";
import fireButtonImgCooldown from "./images/firebutton_cooldown.svg";

// The real modernizr module detects vibrate support once, at import time,
// from whatever navigator jsdom exposes before testUtils' per-test stub is
// installed - too early to control from a test. Mock it so "vibrates when
// supported" is deterministic.
jest.mock("./modernizr", () => ({ vibrate: true }));

function getButton() {
  return screen.getByRole("button", { name: "Fire button" });
}

describe("FireButton - disabled states", () => {
  test("disabled with the no-ammo image when the player has no team", () => {
    render(
      <FireButton user={makeUser({ team_id: null })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText("Fire button").src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("disabled with the no-ammo image when the player has no bullets", () => {
    render(
      <FireButton user={makeUser({ num_bullets: 0 })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText("Fire button").src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("disabled with the no-ammo image when the player has no weapon", () => {
    render(
      <FireButton user={makeUser({ shot_damage: 0 })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText("Fire button").src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("enabled with the normal image when team, bullets and weapon all hold", () => {
    render(<FireButton user={makeUser()} onClick={jest.fn()} />);
    expect(getButton()).toBeEnabled();
    expect(screen.getByAltText("Fire button").src).toContain(fireButtonImg);
  });
});

describe("FireButton - firing", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test("clicking calls onClick, plays the bang sound, and vibrates", () => {
    const onClick = jest.fn();
    render(<FireButton user={makeUser()} onClick={onClick} />);

    fireEvent.click(getButton());

    // onClick itself is fired from a setTimeout(..., 0) inside the handler.
    act(() => {
      jest.advanceTimersByTime(0);
    });

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(getPlaySpy()).toHaveBeenCalled();
    expect(navigator.vibrate).toHaveBeenCalledWith(200);
  });

  test("goes on cooldown after a click: disabled with the cooldown image", () => {
    render(<FireButton user={makeUser()} onClick={jest.fn()} />);

    fireEvent.click(getButton());

    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText("Fire button").src).toContain(
      fireButtonImgCooldown,
    );
  });

  test("re-enables after the default shot_timeout of 6 seconds", () => {
    render(
      <FireButton user={makeUser({ shot_timeout: 6 })} onClick={jest.fn()} />,
    );

    fireEvent.click(getButton());
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(5999);
    });
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText("Fire button").src).toContain(
      fireButtonImgCooldown,
    );

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
    expect(screen.getByAltText("Fire button").src).toContain(fireButtonImg);
  });

  test("a shorter shot_timeout (Eat-a-bullet, 1s) re-enables sooner than the default 6s", () => {
    render(
      <FireButton
        user={makeUser({ shot_damage: 1, shot_timeout: 1 })}
        onClick={jest.fn()}
      />,
    );

    fireEvent.click(getButton());
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(999);
    });
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
  });
});
