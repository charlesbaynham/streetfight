import prose from "./prose";

// The named weapons, shared by every admin page that needs to go from a
// (shot_damage, shot_timeout) pair to a name a human recognises, or the
// other way round. Mirrors WEAPON_NAME_LOOKUP in backend/item_actions.py.
export const WEAPONS = {
  [prose.weapons.noWeapon]: [0, 25],
  [prose.weapons.pewster]: [1, 25],
  [prose.weapons.trackaTracka]: [2, 25],
  [prose.weapons.omg]: [3, 25],
  [prose.weapons.eatABullet]: [1, 5],
};

export function weaponName(user) {
  for (const [name, [damage, timeout]] of Object.entries(WEAPONS)) {
    if (user.shot_damage === damage && user.shot_timeout === timeout)
      return name;
  }
  return null;
}
