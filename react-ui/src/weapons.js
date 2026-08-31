// The named weapons, shared by every admin page that needs to go from a
// (shot_damage, shot_timeout) pair to a name a human recognises, or the
// other way round. Mirrors WEAPON_NAME_LOOKUP in backend/item_actions.py.
export const WEAPONS = {
  "No weapon": [0, 6],
  Pewster: [1, 6],
  "Tracka-Tracka": [2, 6],
  OMG: [3, 6],
  "Eat-a-bullet": [1, 1],
};

export function weaponName(user) {
  for (const [name, [damage, timeout]] of Object.entries(WEAPONS)) {
    if (user.shot_damage === damage && user.shot_timeout === timeout)
      return name;
  }
  return null;
}
