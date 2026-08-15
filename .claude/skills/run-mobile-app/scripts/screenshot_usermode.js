// Drive the streetfight user mode in a mobile viewport and screenshot it.
//
// Usage: node screenshot_usermode.js [output.png] [url-path]
//   e.g. node screenshot_usermode.js usermode.png /
//        node screenshot_usermode.js admin.png /admin
//
// Requires the backend on :8000 and the CRA dev server on :3000 (see
// SKILL.md), plus `npm i playwright` in the current directory. Set
// CHROMIUM_PATH if Chromium is not at /opt/pw-browsers/chromium.
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL || "http://127.0.0.1:3000";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "password";
const OUT = process.argv[2] || "usermode.png";
const PATH = process.argv[3] || "/";

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium",
    args: [
      // Fake webcam (green test pattern) so WebcamView renders headlessly
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
    ],
  });
  const context = await browser.newContext({
    // iPhone 12-ish; the game is mobile-only so never screenshot desktop-sized
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    permissions: ["camera", "geolocation"],
    geolocation: { latitude: 51.4975, longitude: -0.1357 },
  });
  const page = await context.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") console.log("[console.error]", m.text());
  });

  await page.goto(BASE + "/", { waitUntil: "networkidle" });

  // Set a name, then have the "admin" add us to the first team of the sample
  // game and hand out ammo so the HUD is populated (all sharing one cookie
  // jar). NB /api/join_game is dead code - admin_add_user_to_team is how
  // players actually get into a game.
  const setup = await page.evaluate(async (password) => {
    const nameR = await fetch(
      `/api/set_name?name=${encodeURIComponent("Alice")}`,
      { method: "POST" },
    );
    const myId = await (await fetch("/api/my_id")).json();
    const auth = await fetch(
      `/api/admin_authenticate?password=${encodeURIComponent(password)}`,
      { method: "POST" },
    );
    const games = await (await fetch("/api/admin_list_games")).json();
    const teamId = games[0].teams[0].id;
    // Must join a team BEFORE receiving ammo, or admin_give_ammo 500s
    const join = await fetch(
      `/api/admin_add_user_to_team?user_id=${myId}&team_id=${teamId}`,
      { method: "POST" },
    );
    const ammo = await fetch(`/api/admin_give_ammo?user_id=${myId}&num=3`, {
      method: "POST",
    });
    return {
      name: nameR.status,
      auth: auth.status,
      join: join.status,
      ammo: ammo.status,
      myId,
      teamId,
    };
  }, ADMIN_PASSWORD);
  console.log("setup:", JSON.stringify(setup));

  await page.goto(BASE + PATH, { waitUntil: "networkidle" });
  // Permission checks re-poll every 5s; wait one cycle so we leave onboarding
  await page.waitForTimeout(6000);
  await page.screenshot({ path: OUT });
  console.log("screenshot saved to", OUT);

  // Dump visible text so the caller can sanity-check without opening the PNG
  const text = await page.evaluate(() => document.body.innerText);
  console.log("--- page text ---\n" + text);

  await browser.close();
})();
