// Each test re-requires ShotCache.js (and mocks ./utils) via
// jest.resetModules(), because the module keeps its in-flight request map at
// module scope - see the "Module-scope state" note in testUtils.js. Fresh
// modules per test avoid state leaking between cases, in particular for the
// in-flight de-duplication tests.
//
// window.caches itself is reset per-test by setupTests.js (resetTestEnvironment
// -> installFakeCaches), so no jest.resetModules() dance is needed for it.

let ShotCache;
let sendAPIRequest;

beforeEach(() => {
  jest.resetModules();
  jest.doMock("./utils", () => ({ sendAPIRequest: jest.fn() }));

  ShotCache = require("./ShotCache");
  sendAPIRequest = require("./utils").sendAPIRequest;
});

// Mimics the shape sendAPIRequest resolves with: a fetch Response.
function makeApiResponse(body, ok = true) {
  return {
    ok,
    statusText: ok ? "OK" : "Error",
    clone() {
      return makeApiResponse(body, ok);
    },
    json: () => Promise.resolve(body),
  };
}

// Mirrors CURRENT_CACHES.shots in ShotCache.js (`shot-cache-v${CACHE_VERSION}`
// with CACHE_VERSION = 1). Only needed for the one test that primes the cache
// directly rather than going through getShotFromCache.
const CACHE_NAME = "shot-cache-v1";

test("a shot already in the cache is returned without hitting the API", async () => {
  const cache = await global.caches.open(CACHE_NAME);
  await cache.put("shot-1", makeApiResponse({ image_base64: "cached" }));

  const result = await ShotCache.getShotFromCache("shot-1");

  expect(result).toEqual({ image_base64: "cached" });
  expect(sendAPIRequest).not.toHaveBeenCalled();
});

test("a cache miss fetches from admin_get_shot and caches the response, so a second call does not refetch", async () => {
  sendAPIRequest.mockResolvedValue(
    makeApiResponse({ image_base64: "fetched" }),
  );

  const first = await ShotCache.getShotFromCache("shot-2");
  expect(first).toEqual({ image_base64: "fetched" });
  expect(sendAPIRequest).toHaveBeenCalledWith("admin_get_shot", {
    shot_id: "shot-2",
  });
  expect(sendAPIRequest).toHaveBeenCalledTimes(1);

  sendAPIRequest.mockClear();
  const second = await ShotCache.getShotFromCache("shot-2");
  expect(second).toEqual({ image_base64: "fetched" });
  expect(sendAPIRequest).not.toHaveBeenCalled();
});

test("two concurrent requests for the same uncached shot share a single fetch", async () => {
  // getShotFromCache awaits caches.open()/cache.match() before it ever looks
  // at the in-flight map, so both calls below race through those awaits
  // before either reaches sendAPIRequest - resolving the fetch straight away
  // (rather than trying to catch it "mid-flight") keeps this deterministic.
  let resolveFetch;
  const pendingFetch = new Promise((resolve) => {
    resolveFetch = resolve;
  });
  sendAPIRequest.mockReturnValue(pendingFetch);

  const promise1 = ShotCache.getShotFromCache("shot-3");
  const promise2 = ShotCache.getShotFromCache("shot-3");

  resolveFetch(makeApiResponse({ image_base64: "shared" }));

  await expect(promise1).resolves.toEqual({ image_base64: "shared" });
  await expect(promise2).resolves.toEqual({ image_base64: "shared" });
  expect(sendAPIRequest).toHaveBeenCalledTimes(1);
});

test("a falsy shot id resolves to null without touching the cache or the API", async () => {
  const result = await ShotCache.getShotFromCache(undefined);

  expect(result).toBeNull();
  expect(sendAPIRequest).not.toHaveBeenCalled();
  expect(global.caches.open).not.toHaveBeenCalled();
});

test("a failed fetch rejects, and a later call for the same shot retries rather than reusing the rejected promise", async () => {
  sendAPIRequest.mockResolvedValueOnce(makeApiResponse(null, false));

  await expect(ShotCache.getShotFromCache("shot-4")).rejects.toThrow(
    "Error fetching shot",
  );
  expect(sendAPIRequest).toHaveBeenCalledTimes(1);

  sendAPIRequest.mockResolvedValueOnce(
    makeApiResponse({ image_base64: "retry" }),
  );

  const result = await ShotCache.getShotFromCache("shot-4");
  expect(result).toEqual({ image_base64: "retry" });
  expect(sendAPIRequest).toHaveBeenCalledTimes(2);
});
