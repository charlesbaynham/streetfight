import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import {
  ShotHistoryButton,
  ShotHistoryController,
  formatShotTime,
  openShotHistory,
  shotStatus,
} from "./ShotHistory";
import { UpdateSSEConnection } from "./UpdateListener";
import * as shotHistoryStore from "./shotHistoryStore";
import {
  emitUpdate,
  getAPICalls,
  installFetchMock,
  makeShot,
} from "./testUtils";

import checkImg from "./images/check-solid.svg";
import crossImg from "./images/cross.svg";
import returnImg from "./images/return.svg";

afterEach(() => {
  // Belt-and-braces: any test that switches to fake timers restores real
  // ones itself, but this guards against a leak if one doesn't.
  jest.useRealTimers();
});

afterEach(async () => {
  // A test can end while the fetch its mount effect kicked off is still
  // in flight (its assertions didn't depend on the response). Give that
  // promise a macrotask to resolve inside an act() scope - RTL's own
  // afterEach has already unmounted and unsubscribed everything by the
  // time this runs, so a late resolution just lands harmlessly instead of
  // updating whatever mounts in the next test.
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
});

describe("shotStatus", () => {
  test("checked + hit with a target name", () => {
    expect(
      shotStatus(
        makeShot({ checked: true, result: "hit", target_name: "Ann" }),
      ),
    ).toEqual({ icon: checkImg, label: "Hit Ann!" });
  });

  test("checked + hit without a target name", () => {
    expect(
      shotStatus(makeShot({ checked: true, result: "hit", target_name: null })),
    ).toEqual({ icon: checkImg, label: "Hit!" });
  });

  test("checked + refunded", () => {
    expect(shotStatus(makeShot({ checked: true, result: "refunded" }))).toEqual(
      {
        icon: returnImg,
        label: "Ammo refunded",
      },
    );
  });

  test("checked + miss", () => {
    expect(shotStatus(makeShot({ checked: true, result: "miss" }))).toEqual({
      icon: crossImg,
      label: "Missed",
    });
  });

  test("legacy checked shot (result: null) with a target name infers a hit", () => {
    expect(
      shotStatus(makeShot({ checked: true, result: null, target_name: "Ann" })),
    ).toEqual({ icon: checkImg, label: "Hit Ann!" });
  });

  test("legacy checked shot (result: null) without a target name infers a miss", () => {
    expect(
      shotStatus(makeShot({ checked: true, result: null, target_name: null })),
    ).toEqual({ icon: crossImg, label: "Missed" });
  });

  test("unchecked with a completed AI review shows the suggestion and is escalated", () => {
    expect(
      shotStatus(
        makeShot({
          checked: false,
          ai_review_state: "done",
          ai_suggestion: "hit",
        }),
      ),
    ).toEqual({
      emoji: "⏳",
      label: "AI thinks: hit",
      sublabel: "Escalated to referee",
    });
  });

  test.each([
    ["no AI review at all", { ai_review_state: null, ai_suggestion: null }],
    [
      "a pending AI review",
      { ai_review_state: "pending", ai_suggestion: "hit" },
    ],
    ["an errored AI review", { ai_review_state: "error", ai_suggestion: null }],
    [
      "a completed review with no suggestion recorded",
      { ai_review_state: "done", ai_suggestion: null },
    ],
  ])("unchecked, %s, is just 'being reviewed'", (_case, overrides) => {
    expect(shotStatus(makeShot({ checked: false, ...overrides }))).toEqual({
      emoji: "⏳",
      label: "Being reviewed...",
    });
  });
});

describe("formatShotTime", () => {
  test("returns an empty string for an unparseable date", () => {
    expect(formatShotTime("not-a-date")).toBe("");
    expect(formatShotTime(undefined)).toBe("");
  });

  test("returns a locale time string for a valid date", () => {
    const iso = "2026-08-15T10:30:00Z";
    expect(formatShotTime(iso)).toBe(
      new Date(iso).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    );
  });
});

describe("ShotHistoryButton", () => {
  test("renders nothing when there are no shots", async () => {
    installFetchMock({ user_shots: [] });
    await act(() => shotHistoryStore.refreshShots());

    const { container } = render(<ShotHistoryButton />);
    expect(container).toBeEmptyDOMElement();
  });

  test("shows the unseen count as a badge", async () => {
    const shots = [makeShot({ checked: false }), makeShot({ checked: false })];
    installFetchMock({ user_shots: shots });
    await act(() => shotHistoryStore.refreshShots());

    render(<ShotHistoryButton />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  test("shows no badge once every shot has been marked seen", async () => {
    const shots = [makeShot({ checked: false })];
    installFetchMock({ user_shots: shots });
    await act(() => shotHistoryStore.refreshShots());
    shotHistoryStore.markShotsSeen(shots);

    const { container } = render(<ShotHistoryButton />);
    expect(container.querySelector(".badge")).not.toBeInTheDocument();
  });

  test("the standalone prop adds the standalone style class", async () => {
    installFetchMock({ user_shots: [makeShot()] });
    await act(() => shotHistoryStore.refreshShots());

    const { container } = render(<ShotHistoryButton standalone />);
    expect(container.querySelector("button")).toHaveClass(
      "showScoresButton",
      "standalone",
    );
  });

  test("clicking it opens the history popup", async () => {
    installFetchMock({ user_shots: [makeShot()] });
    await act(() => shotHistoryStore.refreshShots());

    render(
      <>
        <ShotHistoryButton />
        <ShotHistoryController />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /My shots/ }));

    expect(
      await screen.findByRole("heading", { name: "My shots" }),
    ).toBeInTheDocument();
  });
});

describe("ShotNotifierBubble (via ShotHistoryController)", () => {
  test("appears when the latest shot's status hasn't been seen", async () => {
    installFetchMock({ user_shots: [makeShot({ checked: false })] });

    const { container } = render(<ShotHistoryController />);
    // Drive the same fetch the mount effect kicked off from inside act(),
    // so the resulting state update is captured rather than landing a tick
    // after the mount effect's own (unwrapped) fetch resolves.
    await act(() => shotHistoryStore.refreshShots());

    expect(container.querySelector(".bubble")).toBeInTheDocument();
  });

  test("is absent once every shot has been seen", async () => {
    const shots = [makeShot({ checked: false })];
    // Seed the seen-map before mounting, matching a returning user whose
    // localStorage already records this exact status as seen.
    shotHistoryStore.markShotsSeen(shots);
    installFetchMock({ user_shots: shots });

    const { container } = render(<ShotHistoryController />);
    // Flush the mount-triggered fetch's resolution (and the resulting,
    // already-seen-so-no-op state update) inside an act() scope, so it
    // can't spill into whatever runs next.
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));

    expect(shotHistoryStore.getShots()).toEqual(shots);
    expect(container.querySelector(".bubble")).not.toBeInTheDocument();
  });

  test("clicking opens the shot's detail view and lingers for 10s before hiding", async () => {
    jest.useFakeTimers();

    const shot = makeShot({ checked: false });
    installFetchMock({ user_shots: [shot] });

    const { container } = render(<ShotHistoryController />);
    await act(() => shotHistoryStore.refreshShots());
    expect(container.querySelector(".bubble")).toBeInTheDocument();

    fireEvent.click(container.querySelector(".bubble"));

    expect(screen.getByText(/All shots/)).toBeInTheDocument();
    // Marking the shot seen as a side effect of opening it would normally
    // hide the bubble, but the post-tap linger keeps it up.
    expect(container.querySelector(".bubble")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(10000);
    });

    expect(container.querySelector(".bubble")).not.toBeInTheDocument();
  });
});

describe("ShotHistoryController", () => {
  test("fetches the shot list on mount and refreshes on a 'user' SSE update", async () => {
    const shotA = makeShot({ checked: false });
    const shotB = makeShot({
      checked: true,
      result: "hit",
      target_name: "Ann",
    });

    let served = [shotA];
    installFetchMock({ user_shots: () => served });

    render(
      <>
        <UpdateSSEConnection />
        <ShotHistoryController />
      </>,
    );

    await waitFor(() => expect(shotHistoryStore.getShots()).toEqual([shotA]));
    expect(getAPICalls("user_shots")).toHaveLength(1);

    served = [shotB];
    act(() => emitUpdate("user"));

    await waitFor(() => expect(shotHistoryStore.getShots()).toEqual([shotB]));
    expect(getAPICalls("user_shots")).toHaveLength(2);
  });

  test("opening the popup marks every shot seen", async () => {
    const shots = [makeShot({ checked: false }), makeShot({ checked: false })];
    installFetchMock({ user_shots: shots });

    // Rendered standalone (no ShotHistoryController in this tree yet) so the
    // list is populated deterministically before the controller mounts.
    await act(() => shotHistoryStore.refreshShots());
    expect(shotHistoryStore.countUnseenShots(shots)).toBe(2);

    render(<ShotHistoryController />);
    await waitFor(() => expect(shotHistoryStore.getShots()).toEqual(shots));

    act(() => openShotHistory());
    await screen.findByRole("heading", { name: "My shots" });

    await waitFor(() =>
      expect(shotHistoryStore.countUnseenShots(shots)).toBe(0),
    );

    const seenMap = JSON.parse(localStorage.getItem("seenShotStatuses"));
    shots.forEach((shot) => {
      expect(seenMap[shot.id]).toBe(
        shotHistoryStore.shotStatusFingerprint(shot),
      );
    });
  });

  // The store's notify() re-delivers the *same* shots array reference after
  // markShotsSeen, so a sibling subscriber whose own state isn't otherwise
  // touched bails out of re-rendering (React skips re-render on an
  // unchanged useState value), leaving its badge showing a stale count
  // until the next refresh actually replaces the array.
  test("BUG: a sibling ShotHistoryButton's badge does not live-update from markShotsSeen alone", async () => {
    const shots = [makeShot({ checked: false }), makeShot({ checked: false })];
    installFetchMock({ user_shots: shots });

    render(
      <>
        <ShotHistoryButton />
        <ShotHistoryController />
      </>,
    );

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /My shots/ }));
    await screen.findByRole("heading", { name: "My shots" });

    // The popup is open and the shots are recorded as seen in localStorage...
    await waitFor(() =>
      expect(shotHistoryStore.countUnseenShots(shots)).toBe(0),
    );

    // ...but the HUD button, a separate subscriber, is still stuck on "2"
    // because its shotList state never actually changed reference.
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  test("openShotHistory(shotId) opens straight onto that shot's detail view, and back returns to the list", async () => {
    const shot = makeShot({ checked: true, result: "hit", target_name: "Ann" });
    installFetchMock({ user_shots: [shot] });

    render(<ShotHistoryController />);
    await waitFor(() => expect(shotHistoryStore.getShots()).toEqual([shot]));

    act(() => openShotHistory(shot.id));

    expect(await screen.findByText("Hit Ann!")).toBeInTheDocument();
    expect(screen.getByText(/All shots/)).toBeInTheDocument();
    expect(screen.queryByText("My shots")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/All shots/));

    expect(
      await screen.findByRole("heading", { name: "My shots" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/All shots/)).not.toBeInTheDocument();
  });

  test("closing the popup clears the selected shot, so reopening shows the list", async () => {
    const shot = makeShot({ checked: false });
    installFetchMock({ user_shots: [shot] });

    const { container } = render(<ShotHistoryController />);
    await waitFor(() => expect(shotHistoryStore.getShots()).toEqual([shot]));

    act(() => openShotHistory(shot.id));
    expect(await screen.findByText(/All shots/)).toBeInTheDocument();

    fireEvent.click(container.querySelector(".exitButton"));
    await waitFor(() =>
      expect(screen.queryByText(/All shots/)).not.toBeInTheDocument(),
    );

    act(() => openShotHistory());

    expect(
      await screen.findByRole("heading", { name: "My shots" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/All shots/)).not.toBeInTheDocument();
  });

  test("thumbnails request each shot's image and render it once resolved", async () => {
    const shotA = makeShot({ id: "shot-a", checked: false });
    const shotB = makeShot({ id: "shot-b", checked: false });

    installFetchMock({
      user_shots: [shotA, shotB],
      user_shot_image: ({ query }) => ({
        image_base64: `data:image/png;base64,${query.shot_id}`,
      }),
    });

    const { container } = render(<ShotHistoryController />);
    act(() => openShotHistory());

    await waitFor(() => {
      const requestedIds = getAPICalls("user_shot_image")
        .map((call) => call.query.shot_id)
        .sort();
      expect(requestedIds).toEqual([shotA.id, shotB.id].sort());
    });

    // Scoped to the row thumbnails (class "thumbnail") rather than
    // getAllByAltText, since both shots are also unseen and the notifier
    // bubble renders its own "Your shot"-alt image for the latest one.
    await waitFor(() => {
      const srcs = Array.from(container.querySelectorAll("img.thumbnail"))
        .map((img) => img.getAttribute("src"))
        .sort();
      expect(srcs).toEqual(
        [
          `data:image/png;base64,${shotA.id}`,
          `data:image/png;base64,${shotB.id}`,
        ].sort(),
      );
    });
  });
});
