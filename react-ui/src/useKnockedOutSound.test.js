import React from "react";
import { render } from "@testing-library/react";

import useKnockedOutSound from "./useKnockedOutSound";
import { getPlaySpy } from "./testMocks/useSound";
import { makeUser } from "./testUtils";

function Harness({ user }) {
  useKnockedOutSound(user);
  return null;
}

// The whole of what is worth testing here is the seeding: "does it play a
// sound" is the browser's job, but "does it play one on a reload" is a bug
// that would go out on thirty phones.
describe("useKnockedOutSound", () => {
  beforeEach(() => getPlaySpy().mockClear());

  test("a player who is already knocked out when the page loads hears nothing", () => {
    const { rerender } = render(
      <Harness user={makeUser({ state: "knocked out" })} />,
    );
    // A second render with the same state - a "user" update that changed
    // something else - must not fire it either.
    rerender(<Harness user={makeUser({ state: "knocked out" })} />);

    expect(getPlaySpy()).not.toHaveBeenCalled();
  });

  test("being knocked out while playing does play it", () => {
    const { rerender } = render(
      <Harness user={makeUser({ state: "alive" })} />,
    );
    expect(getPlaySpy()).not.toHaveBeenCalled();

    rerender(<Harness user={makeUser({ state: "knocked out" })} />);

    expect(getPlaySpy()).toHaveBeenCalledTimes(1);
  });

  test("the seed is the first state that arrives, not the empty one before it", () => {
    // user_info has not landed yet, so UserMode is holding null. If that
    // counted as the seed, the first real state would read as a transition
    // and a reload while knocked out would ding after all.
    const { rerender } = render(<Harness user={null} />);
    rerender(<Harness user={makeUser({ state: "knocked out" })} />);

    expect(getPlaySpy()).not.toHaveBeenCalled();
  });

  test("dying after being knocked out does not play it again", () => {
    const { rerender } = render(
      <Harness user={makeUser({ state: "alive" })} />,
    );
    rerender(<Harness user={makeUser({ state: "knocked out" })} />);
    expect(getPlaySpy()).toHaveBeenCalledTimes(1);

    rerender(<Harness user={makeUser({ state: "dead" })} />);

    expect(getPlaySpy()).toHaveBeenCalledTimes(1);
  });
});
