import { test, expect } from "@playwright/test";
import { desktopFixture } from "./fixtures";
const consoleErrors = new Map<object, string[]>();
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  consoleErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
});
test.afterEach(async ({ page }) => {
  expect(consoleErrors.get(page)).toEqual([]);
});
test("bundled typography and palette reach the rendered controls", async ({
  page,
}) => {
  await desktopFixture(page);
  await page.goto("/");
  const typography = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      font: getComputedStyle(document.body).fontFamily,
      loaded: [...document.fonts].map((font) => ({
        family: font.family,
        status: font.status,
      })),
      forced: matchMedia("(forced-colors: active)").matches,
      selected: getComputedStyle(
        document.querySelector(".navigation .selected")!,
      ).backgroundColor,
    };
  });
  expect(typography.font).toContain("Source Sans 3");
  expect(
    typography.loaded.some(
      (font) =>
        font.family.includes("Source Sans 3") && font.status === "loaded",
    ),
  ).toBe(true);
});
test("a failed option save cannot start a job with stale options", async ({
  page,
}) => {
  await desktopFixture(page, { failSetting: "newest_first" });
  await page.goto("/");
  await page.getByLabel("Newest issues first", { exact: true }).uncheck();
  await expect(page.getByRole("alert")).toContainText(
    "Settings could not be saved",
  );
  await page.getByRole("button", { name: "Track Plans", exact: true }).click();
  await page.getByRole("button", { name: "Magazines", exact: true }).click();
  await page
    .getByRole("button", { name: "Download selected magazines", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Settings could not be saved",
  );
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_QA__.records.some(
        (r: any) => r.command === "start_job",
      ),
    ),
  ).toBe(false);
});
test("all three workflows are available with one visible primary action", async ({
  page,
}) => {
  await desktopFixture(page);
  await page.goto("/");
  await expect(
    page.getByRole("navigation", { name: "Work areas" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Download selected magazines",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Track Plans", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Track plans", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Organize", exact: true }).click();
  await expect(page.getByLabel("Source folder", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Organize PDFs", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Stop job", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop job", exact: true }).click();
  await expect(
    page.getByText("Stopping at the next safe point…", { exact: true }),
  ).toBeVisible();
});
for (const [width, height] of [
  [640, 480],
  [800, 620],
  [1120, 760],
  [1440, 900],
]) {
  for (const dark of [false, true]) {
    test(
      "controls fit " + width + "x" + height + " " + (dark ? "dark" : "light"),
      async ({ page }) => {
        await page.setViewportSize({ width, height });
        await desktopFixture(page, {
          dark,
          expanded: true,
          outcome: "running",
        });
        await page.goto("/");
        await expect(
          page.getByRole("button", { name: "Stop job", exact: true }),
        ).toBeVisible();
        for (const work of ["Magazines", "Track Plans", "Organize"]) {
          await page.getByRole("button", { name: work, exact: true }).click();
          const controls = page.locator("[data-layout-critical]");
          for (const control of await controls.all()) {
            const box = await control.boundingBox();
            expect(box).not.toBeNull();
            if (box) {
              expect(box.x).toBeGreaterThanOrEqual(0);
              expect(box.y).toBeGreaterThanOrEqual(0);
              expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
              expect(box.y + box.height).toBeLessThanOrEqual(height + 1);
            }
          }
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
          ).toBe(true);
          await page.screenshot({
            path:
              "test-results/layout-" +
              width +
              "-" +
              (dark ? "dark" : "light") +
              "-" +
              work.replaceAll(" ", "-") +
              ".png",
          });
        }
        await page.screenshot({
          path:
            "test-results/layout-" +
            width +
            "-" +
            (dark ? "dark" : "light") +
            ".png",
        });
      },
    );
  }
}
test("settings dialog remains usable and supports keyboard dismissal", async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 480 });
  await desktopFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Account & appearance" });
  await expect(dialog).toBeVisible();
  await page
    .getByLabel("Cookie file path", { exact: true })
    .fill("D:/New cookies/session.json");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toBeFocused();
});
test("organizer findings retain counts and safe missing download action", async ({
  page,
}) => {
  await desktopFixture(page, { summary: true });
  await page.goto("/");
  await page.getByRole("button", { name: "Organize", exact: true }).click();
  await expect(
    page.getByText("Metadata updated", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download Missing", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Download Missing", exact: true })
    .click();
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_QA__.records.some(
        (r: any) =>
          r.command === "start_job" && r.args.kind === "download-missing",
      ),
    ),
  ).toBe(true);
});
test("incomplete scan keeps its findings without offering Download Missing", async ({
  page,
}) => {
  await desktopFixture(page, { summary: true, incomplete: true });
  await page.goto("/");
  await page.getByRole("button", { name: "Organize", exact: true }).click();
  await expect(
    page.getByText("Incomplete scan", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download Missing", exact: true }),
  ).toHaveCount(0);
});
test("activity filters retained history, copies errors and clears explicitly", async ({
  page,
}) => {
  await desktopFixture(page, { expanded: true });
  await page.goto("/");
  await page.getByLabel("Filter activity", { exact: true }).fill("network");
  await expect(
    page.getByText("A network request failed 0", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Copy errors", exact: true }).click();
  await page
    .getByRole("button", { name: "Clear activity", exact: true })
    .click();
  await expect(
    page.getByText("No activity yet.", { exact: true }),
  ).toBeVisible();
});

for (const [outcome, label] of [
  ["idle", "Ready"],
  ["running", "Running"],
  ["success", "Complete"],
  ["no-results", "No results"],
  ["failed", "Failed"],
  ["cancelled", "Cancelled"],
]) {
  test(
    "job state " + outcome + " stays reachable in a small window",
    async ({ page }) => {
      await page.setViewportSize({ width: 640, height: 480 });
      await desktopFixture(page, { expanded: true, outcome });
      await page.goto("/");
      await expect(
        page.getByRole("status").getByText(label, { exact: true }),
      ).toBeVisible();
      const header = await page.locator(".activity-header").boundingBox();
      const actions = await page.locator(".workflow-actions").boundingBox();
      const scroll = await page.locator(".work-scroll").boundingBox();
      expect(actions!.y + actions!.height).toBeLessThanOrEqual(header!.y + 1);
      expect(scroll!.y + scroll!.height).toBeLessThanOrEqual(actions!.y + 1);
      await expect(
        page.getByRole("button", { name: "Stop job", exact: true }),
      ).toHaveCount(outcome === "running" ? 1 : 0);
      const events = await page.getByRole("log").boundingBox();
      expect(events!.height).toBeGreaterThanOrEqual(20);
      await page
        .getByRole("button", { name: "Hide Activity", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Show Activity", exact: true }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Show Activity", exact: true })
        .click();
      await page.getByRole("separator", { name: "Resize Activity" }).focus();
      await page.keyboard.press("ArrowDown");
    },
  );
}
test("workflow options, account path and separate destinations are sent before the job", async ({
  page,
}) => {
  await desktopFixture(page);
  await page.goto("/");
  await page.getByLabel("Newest issues first", { exact: true }).uncheck();
  await page.getByLabel("Include special issues", { exact: true }).uncheck();
  await page
    .getByLabel("Test mode (first 3 archive pages)", { exact: true })
    .check();
  await page.getByRole("button", { name: "Clear all", exact: true }).click();
  await page.getByRole("checkbox", { name: /^Model Railroader/ }).check();
  await page
    .getByLabel("Magazine save folder", { exact: true })
    .fill("D:/My magazines");
  await page.keyboard.press("Tab");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Cookie file path", { exact: true })
    .fill("D:/Account/shared.json");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await page.getByRole("button", { name: "Track Plans", exact: true }).click();
  await page
    .getByLabel("Track-plan save folder", { exact: true })
    .fill("D:/Separate plans");
  await page.keyboard.press("Tab");
  await page.getByRole("button", { name: "Magazines", exact: true }).click();
  await page
    .getByRole("button", { name: "Download selected magazines", exact: true })
    .click();
  const records = await page.evaluate(
    () => (window as any).__TRAINS_QA__.records,
  );
  const startIndex = records.findIndex((r: any) => r.command === "start_job");
  expect(records[startIndex].args.kind).toBe("magazines");
  expect(records[startIndex - 1].args.changes).toMatchObject({
    base_dir: "D:/My magazines",
    track_plans_dir: "D:/Separate plans",
    cookies_path: "D:/Account/shared.json",
    newest_first: false,
    include_specials: false,
    test_mode: true,
    selected_magazines: ["Model Railroader"],
  });
});
for (const [label, choice] of [
  ["Cancel", "cancel"],
  ["Minimize to Tray", "tray"],
  ["Stop & Quit", "stop-quit"],
]) {
  test(
    "running close choice " + label + " reaches the desktop",
    async ({ page }) => {
      await page.setViewportSize({ width: 640, height: 480 });
      await desktopFixture(page, { outcome: "running" });
      await page.goto("/");
      await expect(page.getByRole("navigation")).toBeVisible();
      await page.evaluate(() => (window as any).__TRAINS_QA__.emitClose());
      const dialog = page.getByRole("dialog", {
        name: "A job is still running",
      });
      await expect(dialog).toBeVisible();
      await dialog.getByRole("button", { name: label, exact: true }).click();
      await expect(dialog).not.toBeVisible();
      expect(
        await page.evaluate(
          (selected) =>
            (window as any).__TRAINS_QA__.records.some(
              (r: any) =>
                r.command === "close_action" && r.args.choice === selected,
            ),
          choice,
        ),
      ).toBe(true);
    },
  );
}
