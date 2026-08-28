// Each test re-requires shotHistoryStore.js (and mocks ./utils) via
// jest.resetModules(), because the store keeps its state (shots, the
// subscriber set, the getShotImage memoisation map) at module scope. Fresh
// modules per test avoid state leaking between cases, and are required for
// the getShotImage memoisation test in particular.
import { makeShot } from "./testUtils";

let store;
let sendAPIRequest;

beforeEach(() => {
  jest.resetModules();
  jest.doMock("./utils", () => ({ sendAPIRequest: jest.fn() }));

  store = require("./shotHistoryStore");
  sendAPIRequest = require("./utils").sendAPIRequest;
});

function jsonResponse(body, ok = true) {
  return { ok, json: async () => body };
}

// shotStatusFingerprint and isShotStatusSeen are private to
// shotHistoryStore.js as of #113 (the status bubble redesign no longer needs
// them externally) - exercised below only through the public surface
// (markShotsSeen / countUnseenShots), which is what actually matters:
// whether a status change makes a seen shot count as unseen again.
describe("markShotsSeen / countUnseenShots", () => {
  test("a changed checked/result status counts a previously-seen shot as unseen again", () => {
    const shot1 = makeShot({ id: "s1", checked: false });
    const shot2 = makeShot({ id: "s2", checked: false });

    expect(store.countUnseenShots([shot1, shot2])).toBe(2);

    store.markShotsSeen([shot1, shot2]);
    expect(store.countUnseenShots([shot1, shot2])).toBe(0);

    // The shot's status changes after being marked seen: unseen again.
    const shot1Updated = { ...shot1, checked: true, result: "hit" };
    expect(store.countUnseenShots([shot1Updated, shot2])).toBe(1);
  });

  test("a completed AI suggestion counts a previously-seen shot as unseen again", () => {
    const shot = makeShot({
      id: "s1",
      checked: false,
      ai_review_state: null,
      ai_suggestion: null,
    });

    store.markShotsSeen([shot]);
    expect(store.countUnseenShots([shot])).toBe(0);

    const aiDone = { ...shot, ai_review_state: "done", ai_suggestion: "hit" };
    expect(store.countUnseenShots([aiDone])).toBe(1);
  });

  test("a newly-named AI target counts a previously-seen shot as unseen again", () => {
    const shot = makeShot({
      id: "s1",
      checked: false,
      ai_review_state: "done",
      ai_suggestion: "hit",
      ai_target_name: null,
    });

    store.markShotsSeen([shot]);
    expect(store.countUnseenShots([shot])).toBe(0);

    const named = { ...shot, ai_target_name: "Ann" };
    expect(store.countUnseenShots([named])).toBe(1);
  });

  test("an appeal being lodged, and then ruled on, each re-flag the shot as unseen", () => {
    const shot = makeShot({ id: "s1", checked: true, result: "hit" });

    store.markShotsSeen([shot]);
    expect(store.countUnseenShots([shot])).toBe(0);

    const appealed = { ...shot, appeal_state: "open" };
    expect(store.countUnseenShots([appealed])).toBe(1);

    store.markShotsSeen([appealed]);
    expect(store.countUnseenShots([appealed])).toBe(0);

    // The referee rules: news again, to both parties.
    expect(
      store.countUnseenShots([{ ...appealed, appeal_state: "upheld" }]),
    ).toBe(1);
  });

  test("ignores ai_suggestion while ai_review_state is not 'done'", () => {
    const shot = makeShot({
      id: "s1",
      checked: false,
      ai_review_state: null,
      ai_suggestion: null,
    });

    store.markShotsSeen([shot]);

    const pending = {
      ...shot,
      ai_review_state: "pending",
      ai_suggestion: "hit",
    };
    expect(store.countUnseenShots([pending])).toBe(0);

    const nullState = { ...shot, ai_review_state: null, ai_suggestion: "hit" };
    expect(store.countUnseenShots([nullState])).toBe(0);
  });

  test("round-trips seen status through localStorage", () => {
    const shot1 = makeShot({ id: "s1", checked: false });
    const shot2 = makeShot({ id: "s2", checked: false });

    store.markShotsSeen([shot1, shot2]);

    // A fresh module load (as happens on page reload) reads the same
    // localStorage, so a shot marked seen before reload stays seen after.
    jest.resetModules();
    jest.doMock("./utils", () => ({ sendAPIRequest: jest.fn() }));
    const reloadedStore = require("./shotHistoryStore");

    expect(reloadedStore.countUnseenShots([shot1, shot2])).toBe(0);
  });

  test("countUnseenShots handles a null/undefined list", () => {
    expect(store.countUnseenShots(null)).toBe(0);
    expect(store.countUnseenShots(undefined)).toBe(0);
  });

  test("markShotsSeen with an empty list is a no-op", () => {
    localStorage.setItem("seenShotStatuses", JSON.stringify({ foo: "bar" }));
    store.markShotsSeen([]);
    expect(localStorage.getItem("seenShotStatuses")).toBe(
      JSON.stringify({ foo: "bar" }),
    );
  });
});

describe("corrupt localStorage", () => {
  test("corrupt JSON under the seen-map key falls back to an empty map instead of throwing", () => {
    localStorage.setItem("seenShotStatuses", "{not valid json");
    const shot = makeShot({ id: "s1" });

    expect(() => store.countUnseenShots([shot])).not.toThrow();
    expect(store.countUnseenShots([shot])).toBe(1);
  });
});

// The store fetches both halves of the history (fired and received) on every
// refresh; this serves a route table like installFetchMock does for
// components, so a test only has to say what each endpoint returns.
function mockShotEndpoints({ fired = [], received = [] } = {}) {
  sendAPIRequest.mockImplementation((endpoint) => {
    if (endpoint === "user_shots") return Promise.resolve(jsonResponse(fired));
    if (endpoint === "user_shots_received")
      return Promise.resolve(jsonResponse(received));
    return Promise.resolve(jsonResponse(null, false));
  });
}

describe("subscribeShots", () => {
  test("fires on refreshShots and on markShotsSeen, and unsubscribe stops it", async () => {
    const shots = [makeShot({ id: "s1" })];
    mockShotEndpoints({ fired: shots });

    const callback = jest.fn();
    const unsubscribe = store.subscribeShots(callback);

    await store.refreshShots();
    expect(callback).toHaveBeenCalledWith([
      { ...shots[0], direction: "fired" },
    ]);

    callback.mockClear();
    store.markShotsSeen(shots);
    expect(callback).toHaveBeenCalledTimes(1);

    callback.mockClear();
    unsubscribe();

    await store.refreshShots();
    store.markShotsSeen(shots);
    expect(callback).not.toHaveBeenCalled();
  });
});

describe("refreshShots", () => {
  test("leaves the stored list untouched when both endpoints respond non-ok", async () => {
    const initialShots = [makeShot({ id: "s1" })];
    mockShotEndpoints({ fired: initialShots });
    await store.refreshShots();
    expect(store.getShots()).toEqual([
      { ...initialShots[0], direction: "fired" },
    ]);

    sendAPIRequest.mockResolvedValue(jsonResponse(null, false));
    await store.refreshShots();
    expect(store.getShots()).toEqual([
      { ...initialShots[0], direction: "fired" },
    ]);
  });

  test("keeps the half that succeeded when the other endpoint fails", async () => {
    const fired = [makeShot({ id: "s1" })];
    sendAPIRequest.mockImplementation((endpoint) =>
      Promise.resolve(
        endpoint === "user_shots"
          ? jsonResponse(fired)
          : jsonResponse(null, false),
      ),
    );

    await store.refreshShots();
    expect(store.getShots()).toEqual([{ ...fired[0], direction: "fired" }]);
  });

  test("merges the shots fired and the shots received, newest first", async () => {
    const fired = [
      makeShot({ id: "fired-old", time_created: "2026-08-15T10:00:00Z" }),
      makeShot({ id: "fired-new", time_created: "2026-08-15T10:20:00Z" }),
    ];
    const received = [
      makeShot({ id: "received", time_created: "2026-08-15T10:10:00Z" }),
    ];
    mockShotEndpoints({ fired, received });

    await store.refreshShots();

    expect(store.getShots().map((shot) => [shot.id, shot.direction])).toEqual([
      ["fired-new", "fired"],
      ["received", "received"],
      ["fired-old", "fired"],
    ]);
  });

  test("calls both shot-list endpoints", async () => {
    mockShotEndpoints();
    await store.refreshShots();
    expect(sendAPIRequest).toHaveBeenCalledWith("user_shots");
    expect(sendAPIRequest).toHaveBeenCalledWith("user_shots_received");
  });
});

describe("getShotImage", () => {
  test("fetches a shot's image only once and returns the same promise on repeated calls", async () => {
    sendAPIRequest.mockResolvedValue(jsonResponse({ image_base64: "abc123" }));

    const promise1 = store.getShotImage("shot-1");
    const promise2 = store.getShotImage("shot-1");

    // Memoised before either has resolved: same promise instance.
    expect(promise1).toBe(promise2);

    await expect(promise1).resolves.toBe("abc123");
    expect(sendAPIRequest).toHaveBeenCalledTimes(1);

    // Still memoised after resolution.
    store.getShotImage("shot-1");
    expect(sendAPIRequest).toHaveBeenCalledTimes(1);

    expect(sendAPIRequest).toHaveBeenCalledWith("user_shot_image", {
      shot_id: "shot-1",
    });
  });

  test("fetches different shot ids independently", async () => {
    sendAPIRequest.mockResolvedValue(jsonResponse({ image_base64: "img" }));

    store.getShotImage("shot-1");
    store.getShotImage("shot-2");

    expect(sendAPIRequest).toHaveBeenCalledTimes(2);
  });
});
