// The dot colour standing in for a team that has no pinned hat colour yet.
//
// Its own module rather than living in MapView.js because the map and the
// spectator roster must agree on it - reading a dot on the map back to a name
// in the list is the whole point - and every test that stubs the heavy map
// module would otherwise lose the palette with it.
//
// Index-derived, so it is only stable while the set of teams is. A team that
// has been through build_join_codes has a real Team.identity_colour, which is
// the colour of the hat its players are actually wearing; prefer that.
export const FALLBACK_TEAM_COLORS = [
  "red",
  "blue",
  "green",
  "yellow",
  "purple",
  "orange",
  "pink",
  "cyan",
  "brown",
  "black",
];

export function fallbackTeamColour(index) {
  if (index < 0) return null;
  return FALLBACK_TEAM_COLORS[index % FALLBACK_TEAM_COLORS.length];
}
