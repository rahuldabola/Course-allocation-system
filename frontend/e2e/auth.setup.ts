import { expect, test as setup } from "@playwright/test";

// Sign in once per role through the real login page and save the session
// (the JWT lives in localStorage) for the other tests to reuse.
for (const role of ["Admin", "Viewer"] as const) {
  setup(`sign in as ${role}`, async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: new RegExp(`Continue as ${role}`) }).click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.context().storageState({ path: `e2e/.auth/${role.toLowerCase()}.json` });
  });
}
