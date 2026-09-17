import { render, screen, fireEvent, act } from "@testing-library/react";

import FireButton from "./FireButton";
import { makeUser } from "./testUtils";
import { getPlaySpy } from "./testMocks/useSound";
import prose from "./prose";

import fireButtonImg from "./images/firebutton.svg";
import fireButtonImgNoAmmo from "./images/firebutton_no_ammo.svg";
import fireButtonImgCooldown from "./images/firebutton_cooldown.svg";

// The real modernizr module detects vibrate support once, at import time,
// from whatever navigator jsdom exposes before testUtils' per-test stub is
// installed - too early to control from a test. Mock it so "vibrates when
// supported" is deterministic.
jest.mock("./modernizr", () => ({ vibrate: true }));

function getButton() {
  return screen.getByRole("button", { name: prose.fireButton.fireButtonAlt });
}

describe("FireButton - disabled states", () => {
  test("disabled with the no-ammo image when the player has no team", () => {
    render(
      <FireButton user={makeUser({ team_id: null })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("disabled with the no-ammo image when the player has no bullets", () => {
    render(
      <FireButton user={makeUser({ num_bullets: 0 })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("disabled with the no-ammo image when the player has no weapon", () => {
    render(
      <FireButton user={makeUser({ shot_damage: 0 })} onClick={jest.fn()} />,
    );
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgNoAmmo,
    );
  });

  test("enabled with the normal image when team, bullets and weapon all hold", () => {
    render(<FireButton user={makeUser()} onClick={jest.fn()} />);
    expect(getButton()).toBeEnabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImg,
    );
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
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgCooldown,
    );
  });

  test("re-enables after the default shot_timeout of 25 seconds", () => {
    render(
      <FireButton user={makeUser({ shot_timeout: 25 })} onClick={jest.fn()} />,
    );

    fireEvent.click(getButton());
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(24999);
    });
    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgCooldown,
    );

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImg,
    );
  });

  test("a shorter shot_timeout (Eat-a-bullet, 5s) re-enables sooner than the default 25s", () => {
    render(
      <FireButton
        user={makeUser({ shot_damage: 1, shot_timeout: 5 })}
        onClick={jest.fn()}
      />,
    );

    fireEvent.click(getButton());
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(4999);
    });
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
  });
});

// The cooldown is the server's to decide (M1.1): submit_shot refuses a shot
// fired inside one, and UserModel.next_shot_at says when the player may fire
// again. Counting down to that instead of to a local setTimeout is what makes
// a reload come back still cooling rather than handing over a fresh button.
describe("FireButton - the server's cooldown", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // next_shot_at is epoch *seconds*, as the backend sends it.
  const secondsFromNow = (seconds) => (Date.now() + seconds * 1000) / 1000;

  test("a player who arrives mid-cooldown starts disabled, without clicking", () => {
    render(
      <FireButton
        user={makeUser({ shot_timeout: 25, next_shot_at: secondsFromNow(10) })}
        onClick={jest.fn()}
      />,
    );

    expect(getButton()).toBeDisabled();
    expect(screen.getByAltText(prose.fireButton.fireButtonAlt).src).toContain(
      fireButtonImgCooldown,
    );
  });

  test("...and re-enables when the server's moment arrives, not a whole timeout later", () => {
    render(
      <FireButton
        user={makeUser({ shot_timeout: 25, next_shot_at: secondsFromNow(10) })}
        onClick={jest.fn()}
      />,
    );

    act(() => {
      jest.advanceTimersByTime(9999);
    });
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
  });

  test("a next_shot_at already in the past leaves the button ready", () => {
    render(
      <FireButton
        user={makeUser({ shot_timeout: 25, next_shot_at: secondsFromNow(-5) })}
        onClick={jest.fn()}
      />,
    );

    expect(getButton()).toBeEnabled();
  });

  test("a wildly optimistic next_shot_at is clamped to the player's own cooldown", () => {
    // A phone whose clock is hours behind the server's would otherwise read
    // its own cooldown as hours long and lock the player out of the game.
    render(
      <FireButton
        user={makeUser({
          shot_timeout: 25,
          next_shot_at: secondsFromNow(3600),
        })}
        onClick={jest.fn()}
      />,
    );

    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(25000);
    });
    expect(getButton()).toBeEnabled();
  });

  test("a server cooldown longer than the local one wins after a click", () => {
    // The player fires; the server comes back saying they are cooling for
    // longer than this phone thought (a slow round trip, a clock a little
    // behind). The button must not re-enable early and earn them a 403.
    const { rerender } = render(
      <FireButton user={makeUser({ shot_timeout: 5 })} onClick={jest.fn()} />,
    );

    fireEvent.click(getButton());
    expect(getButton()).toBeDisabled();

    rerender(
      <FireButton
        user={makeUser({ shot_timeout: 5, next_shot_at: secondsFromNow(5) })}
        onClick={jest.fn()}
      />,
    );

    act(() => {
      jest.advanceTimersByTime(4999);
    });
    expect(getButton()).toBeDisabled();

    act(() => {
      jest.advanceTimersByTime(1);
    });
    expect(getButton()).toBeEnabled();
  });
});
