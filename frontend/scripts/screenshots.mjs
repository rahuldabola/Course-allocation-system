// Regenerate the README screenshots from a running instance (demo mode).
//   BASE=https://your-app.example npm run screenshots
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const BASE = (process.env.BASE || "http://localhost:3000").replace(/\/$/, "");
const OUT = process.env.OUT || "../docs/screenshots";
const SHOTS = [
  { path: "/", name: "dashboard" },
  { path: "/students", name: "students" },
  { path: "/allocation", name: "allocation" },
];

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();

for (const scheme of ["light", "dark"]) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: scheme,
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  if (scheme === "light") await page.screenshot({ path: `${OUT}/login.png` });
  await page.getByRole("button", { name: /Continue as Admin/ }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();

  for (const shot of SHOTS) {
    await page.goto(`${BASE}${shot.path}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800); // let chart animations settle
    await page.screenshot({ path: `${OUT}/${shot.name}-${scheme}.png` });
  }

  if (scheme === "light") {
    await page.goto(`${BASE}/assistant`);
    await page.getByLabel("Your question").fill("How many SC students got a reserved seat versus an open seat?");
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByRole("button", { name: "View SQL" }).waitFor({ timeout: 60_000 });
    await page.getByRole("button", { name: "View SQL" }).click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/assistant.png` });
  }
  await ctx.close();
}

await browser.close();
console.log(`Screenshots written to ${OUT}`);
