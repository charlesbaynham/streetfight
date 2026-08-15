// Shared test helpers for the React test suite (Jest + React Testing
// Library). This file is imported by setupTests.js to install the global
// jsdom stubs, and by individual test files for the helpers below. It does
// not itself match Jest's testMatch, so it's never run as a test file.
//
// Available helpers:
//
// API mocking / inspection (fetch, driven from a route table):
//   installFetchMock(routes)   - install global.fetch, routed by API endpoint name
//   getAPICalls(endpoint)      - every recorded call to an endpoint: {method, query, body}[]
//   getLastAPICall(endpoint)   - the most recent call to an endpoint, or undefined
//
// SSE (mirrors the wire format UpdateListener.js parses):
//   FakeEventSource            - fake EventSource class (installed as global.EventSource)
//   getEventSources()          - every FakeEventSource instance created so far
//   emitUpdate(type, [es])     - push an "update_prompt" message (e.g. "user", "ticker")
//   emitKeepalive(count, [es]) - push a "keepalive" message
//   emitError([es])            - fire the stream's onerror
//   (es defaults to the most recently created FakeEventSource)
//
// Permissions:
//   setPermission(name, state) - control navigator.permissions.query's resolved state
//   grantAllPermissions()      - convenience: geolocation + camera both "granted"
//
// Fixture factories (override any field via the single `overrides` argument):
//   makeUser(overrides), makeShot(overrides), makeTeam(overrides), makeGame(overrides)
//
// Internal (used by setupTests.js; not normally needed in a test file):
//   resetTestEnvironment()     - reinstalls every global stub fresh, called before each test

// ---------------------------------------------------------------------------
// Fake fetch Response + route-table-driven fetch mock
// ---------------------------------------------------------------------------

function makeFakeResponse(status, body) {
  const ok = status >= 200 && status < 300;
  const bodyIsString = typeof body === "string";

  return {
    ok,
    status,
    statusText: String(status),
    json: () =>
      Promise.resolve(bodyIsString ? JSON.parse(body) : (body ?? null)),
    text: () =>
      Promise.resolve(bodyIsString ? body : JSON.stringify(body ?? null)),
    // Real Response bodies can only be read once; sendAPIRequest relies on
    // clone() to let the error handler and the caller each read the body.
    // This mock's json()/text() are non-destructive already, but clone()
    // returns an equivalent independent object to match the real contract.
    clone() {
      return makeFakeResponse(status, body);
    },
  };
}

let apiCallLog = [];

// Endpoint names are matched exactly as sendAPIRequest passes them to
// makeAPIURL, i.e. without the leading "/api/" (see src/utils.js).
function endpointFromURL(url) {
  return url.pathname.replace(/^\/api\//, "");
}

function parseRequestBody(options) {
  if (!options || options.body === undefined) return undefined;
  try {
    return JSON.parse(options.body);
  } catch (e) {
    return options.body;
  }
}

// An explicit { status, body } spec is distinguished from a plain "200 with
// this JSON body" object by requiring both keys together - none of the
// fixture shapes in this file use both "status" and "body" as field names.
function isExplicitSpec(spec) {
  return (
    spec !== null &&
    typeof spec === "object" &&
    "status" in spec &&
    "body" in spec
  );
}

// Install a fetch mock driven by a route table: { endpointName: spec }.
// spec may be:
//   - a plain object/array -> resolves 200 with that JSON body
//   - { status, body }     -> resolves with that explicit status/body
//   - a function({method, query, body}) -> returning either of the above
// Endpoints not present in the table resolve 404 rather than throwing, so an
// unexpected call fails assertions instead of crashing the test.
export function installFetchMock(routes = {}) {
  apiCallLog = [];

  global.fetch = jest.fn((input, options = {}) => {
    const url =
      input instanceof URL ? input : new URL(input, "http://localhost");
    const endpoint = endpointFromURL(url);
    const method = options.method || "GET";
    const query = Object.fromEntries(url.searchParams.entries());
    const body = parseRequestBody(options);

    apiCallLog.push({ endpoint, method, query, body });

    let spec = routes[endpoint];
    if (typeof spec === "function") spec = spec({ method, query, body });

    if (spec === undefined) {
      return Promise.resolve(
        makeFakeResponse(404, { error: "not mocked", endpoint }),
      );
    }

    if (isExplicitSpec(spec)) {
      return Promise.resolve(makeFakeResponse(spec.status, spec.body));
    }
    return Promise.resolve(makeFakeResponse(200, spec));
  });

  return global.fetch;
}

// The default fetch stub installed before every test even when a test
// doesn't call installFetchMock: any unmocked call resolves 404-ish rather
// than throwing "fetch is not defined".
function installDefaultFetchStub() {
  apiCallLog = [];
  global.fetch = jest.fn(() =>
    Promise.resolve(
      makeFakeResponse(404, { error: "no fetch mock installed" }),
    ),
  );
}

export function getAPICalls(endpoint) {
  return apiCallLog.filter((call) => call.endpoint === endpoint);
}

export function getLastAPICall(endpoint) {
  const calls = getAPICalls(endpoint);
  return calls[calls.length - 1];
}

// ---------------------------------------------------------------------------
// Fake EventSource (jsdom has none) matching UpdateSSEConnection's usage in
// src/UpdateListener.js: it only ever sets .onmessage/.onerror and calls
// .close(), so that's all this needs to implement.
// ---------------------------------------------------------------------------

let eventSourceInstances = [];

export class FakeEventSource {
  constructor(url) {
    this.url = String(url);
    this.onmessage = null;
    this.onerror = null;
    this.onopen = null;
    this.readyState = 0; // CONNECTING
    eventSourceInstances.push(this);
  }

  close() {
    this.readyState = 2; // CLOSED
  }
}

function resetEventSources() {
  eventSourceInstances = [];
}

export function getEventSources() {
  return eventSourceInstances;
}

function latestEventSource() {
  return eventSourceInstances[eventSourceInstances.length - 1];
}

function deliverMessage(es, payload) {
  if (!es) throw new Error("No FakeEventSource instance available to emit on");
  if (es.onmessage) es.onmessage({ data: JSON.stringify(payload) });
}

// Push an "update_prompt" message for the given update type ("user",
// "ticker", "shots", "admin", "circle", ...), matching processMessage in
// UpdateListener.js.
export function emitUpdate(type, es = latestEventSource()) {
  deliverMessage(es, { handler: "update_prompt", data: type });
}

// Push a "keepalive" message with the given incrementing count.
export function emitKeepalive(count, es = latestEventSource()) {
  deliverMessage(es, { handler: "keepalive", data: count });
}

// Fire the stream's onerror handler (simulates a dropped connection).
export function emitError(es = latestEventSource()) {
  if (!es) throw new Error("No FakeEventSource instance available to emit on");
  if (es.onerror) es.onerror(new Event("error"));
}

// ---------------------------------------------------------------------------
// Permissions API stub
// ---------------------------------------------------------------------------

let permissionState = {};

function defaultPermissionState() {
  return { geolocation: "prompt", camera: "prompt" };
}

export function setPermission(name, state) {
  permissionState[name] = state;
}

export function grantAllPermissions() {
  setPermission("geolocation", "granted");
  setPermission("camera", "granted");
}

function queryPermission({ name }) {
  return Promise.resolve({ state: permissionState[name] || "prompt" });
}

// ---------------------------------------------------------------------------
// Fixture factories
//
// Field names come from the Pydantic schemas in backend/model.py
// (UserModel, ShotModel, TeamModel, GameModel), cross-checked against how
// the frontend actually reads them (src/UserMode.js, src/BulletCount.js,
// src/ShotHistory.js, src/shotHistoryStore.js). target_name and
// ai_suggestion aren't raw ShotModel columns - they're admin/AI-review
// annotations the API adds - but they're included since ShotHistory.js reads
// them directly off each shot.
// ---------------------------------------------------------------------------

let fixtureIdCounter = 0;
function nextFixtureId(prefix) {
  fixtureIdCounter += 1;
  return `${prefix}-${fixtureIdCounter}`;
}

export function makeUser(overrides = {}) {
  return {
    id: nextFixtureId("user"),
    name: "Test Player",
    team_id: nextFixtureId("team"),
    team_name: "Red Team",
    active: true,
    state: "alive", // "alive" | "knocked out" | "dead"
    hit_points: 3,
    num_bullets: 5,
    shot_damage: 1,
    shot_timeout: 6,
    ...overrides,
  };
}

export function makeShot(overrides = {}) {
  return {
    id: nextFixtureId("shot"),
    checked: false,
    result: null,
    target_name: null,
    time_created: new Date().toISOString(),
    ai_review_state: null,
    ai_suggestion: null,
    ...overrides,
  };
}

export function makeTeam(overrides = {}) {
  return {
    id: nextFixtureId("team"),
    name: "Red Team",
    game_id: nextFixtureId("game"),
    users: [],
    ...overrides,
  };
}

export function makeGame(overrides = {}) {
  return {
    id: nextFixtureId("game"),
    teams: [],
    ticker_update_tag: 0,
    active: true,
    ai_shot_review_enabled: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Global stub installation - called from setupTests.js before every test
// ---------------------------------------------------------------------------

function installFakeCaches() {
  // cacheName -> Map(key -> value), kept for the lifetime of one test
  const cacheStore = new Map();

  function handleFor(name) {
    if (!cacheStore.has(name)) cacheStore.set(name, new Map());
    const store = cacheStore.get(name);
    return {
      match: jest.fn((key) => Promise.resolve(store.get(String(key)))),
      put: jest.fn((key, value) => {
        store.set(String(key), value);
        return Promise.resolve();
      }),
    };
  }

  global.caches = {
    open: jest.fn((name) => Promise.resolve(handleFor(name))),
    keys: jest.fn(() => Promise.resolve(Array.from(cacheStore.keys()))),
    delete: jest.fn((name) => Promise.resolve(cacheStore.delete(name))),
  };
}

// Reinstalls every global stub this suite relies on, fresh. Called from a
// beforeEach in setupTests.js so no state (fetch call log, SSE instances,
// permission overrides, mock call history) leaks between tests.
export function resetTestEnvironment() {
  localStorage.clear();
  jest.clearAllMocks(); // clears call history on module-scoped mocks (testMocks/*) too

  permissionState = defaultPermissionState();
  resetEventSources();
  installDefaultFetchStub();

  global.EventSource = FakeEventSource;

  Object.defineProperty(window.navigator, "permissions", {
    configurable: true,
    value: { query: jest.fn(queryPermission) },
  });

  Object.defineProperty(window.navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: jest.fn(),
      watchPosition: jest.fn(),
      clearWatch: jest.fn(),
    },
  });

  Object.defineProperty(window.navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: jest.fn(() =>
        Promise.resolve({ getTracks: () => [{ stop: jest.fn() }] }),
      ),
    },
  });

  Object.defineProperty(window.navigator, "vibrate", {
    configurable: true,
    value: jest.fn(),
  });

  window.confirm = jest.fn(() => true);
  window.alert = jest.fn();
  window.scrollTo = jest.fn();

  installFakeCaches();
}
