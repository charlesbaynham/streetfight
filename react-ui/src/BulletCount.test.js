import React from "react";
import { render, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import BulletCount from "./BulletCount";
import TemporaryOverlay from "./TemporaryOverlay";
import { makeUser, installFetchMock, getAPICalls } from "./testUtils";
import { getGunImgFromUser } from "./utils";
import styles from "./BulletCount.module.css";

import bullet from "./images/art/bullet.png";
import armourImg from "./images/art/helmet.png";
import cross from "./images/cross.svg";
import medkit from "./images/art/medkit.png";

// TemporaryOverlay drives its own async, sound-and-vibration-triggering
// animation lifecycle (see TemporaryOverlay.js), which is irrelevant to what
// BulletCount itself is responsible for: deciding *when* each overlay's
// "appear" prop should go true. Mock it with a jest.fn() so every prop it
// was ever called with - including transient renders that never make it
// into the final settled DOM - can be inspected via .mock.calls.
jest.mock("./TemporaryOverlay", () => jest.fn(() => null));

function renderBulletCount(user, initialEntries = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <BulletCount user={user} />
    </MemoryRouter>,
  );
}

function rerenderBulletCount(rerender, user, initialEntries = ["/"]) {
  rerender(
    <MemoryRouter initialEntries={initialEntries}>
      <BulletCount user={user} />
    </MemoryRouter>,
  );
}

function callsFor(img) {
  return TemporaryOverlay.mock.calls
    .map(([props]) => props)
    .filter((p) => p.img === img);
}

function everAppeared(img) {
  return callsFor(img).some((p) => p.appear === true);
}

describe("ammo display", () => {
  test.each([1, 2, 3])("shows %i bullet icon(s) with no count text", (n) => {
    const { container } = renderBulletCount(makeUser({ num_bullets: n }));
    const ammoPara = container.querySelectorAll("p")[0];
    const imgs = ammoPara.querySelectorAll("img");
    expect(imgs).toHaveLength(n);
    imgs.forEach((img) => expect(img.src).toContain(bullet));
    expect(ammoPara.textContent).not.toContain("x");
  });

  test("shows a single bullet icon plus a count above 3", () => {
    const { container } = renderBulletCount(makeUser({ num_bullets: 5 }));
    const ammoPara = container.querySelectorAll("p")[0];
    const imgs = ammoPara.querySelectorAll("img");
    expect(imgs).toHaveLength(1);
    expect(imgs[0].src).toContain(bullet);
    expect(ammoPara.textContent).toContain("x5");
  });

  test("shows a cross at 0 bullets", () => {
    const { container } = renderBulletCount(makeUser({ num_bullets: 0 }));
    const ammoPara = container.querySelectorAll("p")[0];
    const imgs = ammoPara.querySelectorAll("img");
    expect(imgs).toHaveLength(1);
    expect(imgs[0].src).toContain(cross);
  });
});

describe("armour display", () => {
  test("shows hit_points - 1 armour icons", () => {
    const { container } = renderBulletCount(makeUser({ hit_points: 4 }));
    const armourPara = container.querySelectorAll("p")[1];
    const imgs = armourPara.querySelectorAll("img");
    expect(imgs).toHaveLength(3);
    imgs.forEach((img) => expect(img.src).toContain(armourImg));
  });

  test.each([1, 0])("shows a cross when hit_points is %i", (hp) => {
    const { container } = renderBulletCount(makeUser({ hit_points: hp }));
    const armourPara = container.querySelectorAll("p")[1];
    const imgs = armourPara.querySelectorAll("img");
    expect(imgs).toHaveLength(1);
    expect(imgs[0].src).toContain(cross);
  });
});

describe("weapon image", () => {
  test.each([
    [1, 6],
    [2, 6],
    [3, 6],
    [1, 1],
  ])(
    "matches getGunImgFromUser for shot_damage=%i shot_timeout=%i",
    (shot_damage, shot_timeout) => {
      const user = makeUser({ shot_damage, shot_timeout });
      const { container } = renderBulletCount(user);
      const weaponImg = container.querySelector(`.${styles.weaponImg}`);
      expect(weaponImg.src).toContain(getGunImgFromUser(user));
    },
  );
});

describe("pickup overlays", () => {
  test("no overlay is told to appear on first render (there is no previous user to compare against)", () => {
    renderBulletCount(makeUser());
    expect(
      TemporaryOverlay.mock.calls.some(([props]) => props.appear === true),
    ).toBe(false);
  });

  test("bullets increasing tells the bullet overlay to appear, and no other overlay", () => {
    const user = makeUser({ num_bullets: 2 });
    const { rerender } = renderBulletCount(user);
    rerenderBulletCount(rerender, { ...user, num_bullets: 3 });

    expect(everAppeared(bullet)).toBe(true);
    expect(everAppeared(armourImg)).toBe(false);
    expect(everAppeared(medkit)).toBe(false);
    expect(everAppeared(getGunImgFromUser(user))).toBe(false);
  });

  test("hit points increasing from above zero tells the armour overlay to appear, not the medpack overlay", () => {
    const user = makeUser({ hit_points: 2 });
    const { rerender } = renderBulletCount(user);
    rerenderBulletCount(rerender, { ...user, hit_points: 3 });

    expect(everAppeared(armourImg)).toBe(true);
    expect(everAppeared(medkit)).toBe(false);
  });

  test("hit points going 0 -> 1 tells the medpack overlay to appear, not the armour overlay", () => {
    const user = makeUser({ hit_points: 0 });
    const { rerender } = renderBulletCount(user);
    rerenderBulletCount(rerender, { ...user, hit_points: 1 });

    expect(everAppeared(medkit)).toBe(true);
    expect(everAppeared(armourImg)).toBe(false);
  });

  test("a change of shot_damage or shot_timeout tells the gun overlay to appear, and no other overlay", () => {
    const user = makeUser({ shot_damage: 1, shot_timeout: 6 });
    const updatedUser = { ...user, shot_damage: 2 };
    const { rerender } = renderBulletCount(user);
    rerenderBulletCount(rerender, updatedUser);

    expect(everAppeared(getGunImgFromUser(updatedUser))).toBe(true);
    expect(everAppeared(bullet)).toBe(false);
    expect(everAppeared(armourImg)).toBe(false);
    expect(everAppeared(medkit)).toBe(false);
  });

  // Bug: BulletCount's overlay-triggering effect (in BulletCount.js) lists
  // `previousUser` as a dependency but also unconditionally sets it via
  // setPreviousUser(user) on every run. The moment a real pickup sets a
  // show*Anim flag true, that same setPreviousUser call makes `previousUser`
  // equal `user`, which re-triggers the effect (deps changed) and - since
  // user and previousUser now compare equal - immediately flips the flag
  // back to false again. This all happens synchronously, well before any
  // wall-clock time passes, so the nominal setTimeout(..., 3000) "clear the
  // overlay after 3s" branch is cancelled (via the effect's own cleanup)
  // before it ever gets a chance to fire. The visible animation still plays
  // because TemporaryOverlay latches onto the momentary appear=true itself,
  // but BulletCount's own flag does not stay true for 3 seconds.
  test("the appear flag is undone again in the very next render, well before the nominal 3-second auto-clear can run", () => {
    jest.useFakeTimers();
    const user = makeUser({ num_bullets: 2 });
    const { rerender } = renderBulletCount(user);
    rerenderBulletCount(rerender, { ...user, num_bullets: 3 });

    expect(everAppeared(bullet)).toBe(true);
    expect(callsFor(bullet).at(-1).appear).toBe(false);

    const callCountBeforeWait = TemporaryOverlay.mock.calls.length;
    act(() => {
      jest.advanceTimersByTime(3000);
    });
    // Nothing further happens at the 3-second mark: the auto-clear timer
    // that would have flipped it false was already cancelled.
    expect(TemporaryOverlay.mock.calls.length).toBe(callCountBeforeWait);

    jest.useRealTimers();
  });
});

describe("item collection alongside a pickup overlay", () => {
  test("a collect_item request still fires shortly after a pickup, despite the overlay animation still playing", async () => {
    jest.useFakeTimers();
    installFetchMock({ collect_item: {} });

    const user = makeUser({ num_bullets: 2 });
    const { rerender } = renderBulletCount(user, ["/?d=SOME_CODE"]);

    act(() => {
      jest.advanceTimersByTime(50);
    });
    rerenderBulletCount(rerender, { ...user, num_bullets: 3 }, [
      "/?d=SOME_CODE",
    ]);

    // No request yet - the debounce inside CollectItemFromQueryParam hasn't
    // elapsed.
    expect(getAPICalls("collect_item")).toHaveLength(0);

    // BulletCount is meant to suppress collection via enabled={!anyActive}
    // while a pickup overlay is showing, but per the bug documented above,
    // anyActive only stays true for a single synchronous render - so the
    // suppression window is effectively zero wall-clock time and the
    // request still fires on its normal ~200ms debounce.
    await act(async () => {
      jest.advanceTimersByTime(250);
      // Flush the microtasks in the collect_item promise chain (fetch ->
      // sendAPIRequest's .then -> the component's own .then/.then/navigate).
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(getAPICalls("collect_item")).toHaveLength(1);
    expect(getAPICalls("collect_item")[0].body).toEqual({
      data: "SOME_CODE",
    });

    jest.useRealTimers();
  });
});
