import prose from "./prose";

// The named weapons, shared by every admin page that needs to go from a
// (shot_damage, shot_timeout) pair to a name a human recognises, or the
// other way round. Mirrors WEAPON_NAME_LOOKUP in backend/item_actions.py.
export const WEAPONS = {
  [prose.weapons.noWeapon]: [0, 6],
  [prose.weapons.pewster]: [1, 6],
  [prose.weapons.trackaTracka]: [2, 6],
  [prose.weapons.omg]: [3, 6],
  [prose.weapons.eatABullet]: [1, 1],
};

export function weaponName(user) {
  for (const [name, [damage, timeout]] of Object.entries(WEAPONS)) {
    if (user.shot_damage === damage && user.shot_timeout === timeout)
      return name;
  }
  return null;
}
