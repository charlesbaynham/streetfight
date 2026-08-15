// Mock for the `use-sound` package, wired in via `moduleNameMapper` in
// package.json. The real hook decodes audio through the Web Audio API, which
// jsdom doesn't implement, so every component that calls useSound(...) gets
// this stand-in default export instead.
//
// Usage in a test:
//   import { getPlaySpy } from "../testMocks/useSound";
//   // ...render a component that calls useSound()...
//   expect(getPlaySpy()).toHaveBeenCalled();

// A single stable spy shared by every call to the hook, so tests don't need
// to intercept the hook call itself to get at it.
const play = jest.fn();

export default function useSound() {
  return [play, {}];
}

export function getPlaySpy() {
  return play;
}
