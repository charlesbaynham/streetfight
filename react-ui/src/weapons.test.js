import fs from "fs";
import path from "path";

import { weaponName } from "./weapons";

describe("weaponName", () => {
  test.each([
    [{ shot_damage: 0, shot_timeout: 6 }, "No weapon"],
    [{ shot_damage: 1, shot_timeout: 6 }, "Pewster"],
    [{ shot_damage: 2, shot_timeout: 6 }, "Tracka-Tracka"],
    [{ shot_damage: 3, shot_timeout: 6 }, "OMG"],
    [{ shot_damage: 1, shot_timeout: 1 }, "Eat-a-bullet"],
  ])("maps %j to %s", (user, expected) => {
    expect(weaponName(user)).toBe(expected);
  });

  test("returns null for a damage/timeout combination not in the table", () => {
    expect(weaponName({ shot_damage: 9, shot_timeout: 9 })).toBeNull();
    expect(weaponName({ shot_damage: 2, shot_timeout: 1 })).toBeNull();
  });

  // The frontend keeps its own copy of the backend's WEAPON_NAME_LOOKUP
  // (comment above WEAPONS in weapons.js says so) instead of fetching it, so
  // nothing catches the two drifting apart except a test that reads both.
  test("matches WEAPON_NAME_LOOKUP in backend/item_actions.py", () => {
    const backendSource = fs.readFileSync(
      path.join(__dirname, "..", "..", "backend", "item_actions.py"),
      "utf8",
    );
    const lookupBlock = backendSource.match(
      /WEAPON_NAME_LOOKUP = \{([\s\S]*?)\n\}/,
    );
    expect(lookupBlock).not.toBeNull(); // sanity: the parse itself didn't silently find nothing

    const backendEntries = [
      ...lookupBlock[1].matchAll(/\((\d+),\s*(\d+)\):\s*"([^"]+)"/g),
    ].map(([, damage, timeout, name]) => ({
      damage: Number(damage),
      timeout: Number(timeout),
      name,
    }));
    expect(backendEntries.length).toBeGreaterThan(0);

    // Every backend entry maps to the same name on the frontend...
    for (const { damage, timeout, name } of backendEntries) {
      expect(weaponName({ shot_damage: damage, shot_timeout: timeout })).toBe(
        name,
      );
    }

    // ...and the frontend doesn't recognise anything the backend doesn't.
    const known = new Set(
      backendEntries.map((e) => `${e.damage},${e.timeout}`),
    );
    for (let damage = 0; damage <= 4; damage++) {
      for (const timeout of [0, 1, 2, 6, 7]) {
        if (!known.has(`${damage},${timeout}`)) {
          expect(
            weaponName({ shot_damage: damage, shot_timeout: timeout }),
          ).toBeNull();
        }
      }
    }
  });
});
