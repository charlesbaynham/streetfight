import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

import TeamLeaderPanel, { TeamLeaderButton } from "./TeamLeaderPanel";
import prose from "./prose";

describe("TeamLeaderPanel", () => {
  test("shows nothing at all to a player who is not a leader", () => {
    const { container } = render(
      <TeamLeaderPanel user={{ is_team_leader: false }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("shows the checklist to a leader", () => {
    render(<TeamLeaderPanel user={{ is_team_leader: true }} />);

    expect(screen.getByText(prose.teamLeader.heading)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(
      prose.teamLeader.checklist.length,
    );
  });
});

describe("TeamLeaderButton", () => {
  test("offers nothing to a player who is not a leader", () => {
    const { container } = render(
      <TeamLeaderButton user={{ is_team_leader: false }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("keeps the checklist behind a tap for a leader", () => {
    render(<TeamLeaderButton user={{ is_team_leader: true }} />);

    expect(
      screen.queryByText(prose.teamLeader.heading),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(prose.teamLeader.buttonText));

    expect(screen.getByText(prose.teamLeader.heading)).toBeInTheDocument();
  });
});
