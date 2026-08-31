import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import NewItems from "./NewItems";
import { installFetchMock, getLastAPICall, actAndFlush } from "./testUtils";

test("the weapon item type offers a dropdown of named weapons, not raw number fields", async () => {
  installFetchMock({
    admin_make_new_item: {
      itype: "weapon",
      item_data: {},
      encoded_item: "ENC",
      encoded_url: "https://example.com?i=ENC",
    },
  });
  render(<NewItems />);

  await actAndFlush(() =>
    userEvent.selectOptions(screen.getByRole("combobox"), "weapon"),
  );

  expect(screen.queryByText("shot_damage:")).not.toBeInTheDocument();
  expect(screen.queryByText("shot_timeout:")).not.toBeInTheDocument();

  const weaponSelect = screen.getByText("weapon:").nextSibling;
  expect(weaponSelect.tagName).toBe("SELECT");
  // "No weapon" is meaningless as a loot drop - it's only ever a player's
  // per-slot state, never something to hand out.
  expect(
    screen.queryByRole("option", { name: "No weapon" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Pewster" })).toBeInTheDocument();
});

test("picking a named weapon posts its damage/timeout pair as the item data", async () => {
  installFetchMock({
    admin_make_new_item: {
      itype: "weapon",
      item_data: {},
      encoded_item: "ENC",
      encoded_url: "https://example.com?i=ENC",
    },
  });
  render(<NewItems />);

  await actAndFlush(() =>
    userEvent.selectOptions(screen.getByRole("combobox"), "weapon"),
  );
  await actAndFlush(() =>
    userEvent.selectOptions(
      screen.getByText("weapon:").nextSibling,
      "Tracka-Tracka",
    ),
  );

  const call = getLastAPICall("admin_make_new_item");
  expect(call.query.item_type).toBe("weapon");
  expect(call.body).toEqual({ shot_damage: 2, shot_timeout: 6 });
});

test("a non-weapon item type still uses plain number fields", async () => {
  installFetchMock({
    admin_make_new_item: {
      itype: "weapon",
      item_data: {},
      encoded_item: "ENC",
      encoded_url: "https://example.com?i=ENC",
    },
  });
  render(<NewItems />);

  expect(screen.getByText("num:")).toBeInTheDocument();
  const numInput = screen.getByText("num:").nextSibling;
  expect(numInput.tagName).toBe("INPUT");
  expect(numInput).toHaveAttribute("type", "number");
});
