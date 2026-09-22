import { expect, test, type Page } from "@playwright/test";

// Sessions saved by auth.setup.ts (one real login per role).
const ADMIN = "e2e/.auth/admin.json";
const VIEWER = "e2e/.auth/viewer.json";

async function openDashboard(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test.describe("signed out", () => {
  test("visitors are sent to the login page", async ({ page }) => {
    await page.goto("/students");
    await expect(page).toHaveURL(/\/login\?next=%2Fstudents/);
    await expect(page.getByRole("heading", { name: "Sign in to CourseAlloc" })).toBeVisible();
  });

  test("a wrong password shows an error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@demo.edu");
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText("Incorrect email or password")).toBeVisible();
  });
});

test.describe("as admin", () => {
  test.use({ storageState: ADMIN });

  test("dashboard shows the seeded demo data", async ({ page }) => {
    await openDashboard(page);
    await expect(page.getByText(/\d+ courses · \d+ seats/)).toBeVisible();
    await expect(page.getByText(/\d+% of students placed/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Preference satisfaction" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Course breakdown" })).toBeVisible();
  });

  test("can add a course and a student, then allocate them", async ({ page }) => {
    const suffix = Date.now().toString().slice(-6);
    const course = `E2E Robotics ${suffix}`;
    const roll = `E2E${suffix}`;
    await openDashboard(page);

    await page.getByRole("link", { name: "Courses", exact: true }).click();
    await page.getByRole("button", { name: "Add course" }).first().click();
    await page.getByLabel("Course name").fill(course);
    await page.getByLabel("Total seats").fill("5");
    await page.getByRole("button", { name: "Create course" }).click();
    await expect(page.getByRole("cell", { name: course, exact: true })).toBeVisible();

    await page.getByRole("link", { name: "Students", exact: true }).click();
    await page.getByRole("button", { name: "Add student" }).click();
    await page.getByLabel("Roll number").fill(roll);
    await page.getByLabel("Full name").fill("E2E Tester");
    await page.getByLabel("Entrance marks").fill("99.9");
    await page.getByLabel("Preference 1").selectOption({ label: `1. ${course}` });
    await page.getByRole("button", { name: "Register student" }).click();
    await expect(page.getByText("Registered E2E Tester.")).toBeVisible();

    await page.getByRole("link", { name: "Allocation", exact: true }).click();
    await page.getByRole("button", { name: "Run allocation" }).click();
    await expect(page.getByText(/Allocated \d+ of \d+ students/)).toBeVisible();
    await page.getByLabel("Search").fill(roll);
    const row = page.getByRole("row", { name: /E2E Tester/ });
    await expect(row).toContainText(course);
    await expect(row).toContainText("1st choice");
  });

  test.describe("mobile layout", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    for (const path of ["/", "/students", "/courses", "/allocation", "/assistant"]) {
      test(`no horizontal overflow on ${path}`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await page.waitForLoadState("networkidle");
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow).toBeLessThanOrEqual(0);
      });
    }
  });
});

test.describe("as viewer", () => {
  test.use({ storageState: VIEWER });

  test("the UI is read-only", async ({ page }) => {
    await openDashboard(page);
    await expect(page.getByRole("button", { name: "Run allocation" })).toHaveCount(0);
    await page.getByRole("link", { name: "Students", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Students" })).toBeVisible();
    await expect(page.getByText(/\d+ students?$/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Add student" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Delete / })).toHaveCount(0);
    await page.getByRole("link", { name: "Allocation", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Allocation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Run allocation" })).toHaveCount(0);
  });

  test("the assistant answers a report question and shows its SQL", async ({ page }) => {
    await page.goto("/assistant");
    await page.getByLabel("Your question").fill("Category-wise allocation summary");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByRole("button", { name: "View SQL" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "View SQL" }).click();
    await expect(page.locator("pre")).toContainText("SELECT");
  });
});
