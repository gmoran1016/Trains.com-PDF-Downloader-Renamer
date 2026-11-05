import { expect, test } from "@playwright/test";
import { desktopFixture } from "./fixtures";

const portableAsset =
  "https://github.com/gmoran1016/Trains.com-PDF-Downloader-Renamer/releases/latest/download/TrainsDownloader-windows.exe";

test("a startup update is offered without downloading before consent", async ({
  page,
}) => {
  await desktopFixture(page, {
    update: { version: "2.0.1", notes: "Improves archive downloads." },
  });
  await page.goto("/");

  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("2.0.0");
  await expect(dialog).toContainText("2.0.1");
  await expect(dialog).toContainText("Improves archive downloads.");
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_UPDATER_QA__.records.some(
        (record: any) => record.action === "install",
      ),
    ),
  ).toBe(false);
});

test("choosing Later leaves installation available through Settings", async ({
  page,
}) => {
  await desktopFixture(page, { update: { version: "2.0.1" } });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Later", exact: true }).click();
  await expect(dialog).not.toBeVisible();

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Account & appearance" });
  await expect(settings).toContainText("Update available: 2.0.1");
  await expect(
    settings.getByRole("button", { name: "Check for updates", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_UPDATER_QA__.records.some(
        (record: any) => record.action === "install",
      ),
    ),
  ).toBe(false);
});

test("accepted update reports progress then relaunches", async ({ page }) => {
  await desktopFixture(page, { update: { version: "2.0.1" } });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Install and restart", exact: true })
    .click();
  await expect(dialog).toContainText("Downloading update");
  await expect(dialog).toContainText("65%");
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as any).__TRAINS_UPDATER_QA__.records.map(
          (record: any) => record.action,
        ),
      ),
    )
    .toEqual(["check", "install", "relaunch"]);
});

test("an install failure stays visible and does not relaunch", async ({ page }) => {
  await desktopFixture(page, {
    update: { version: "2.0.1" },
    installError: "The signed update could not be installed.",
  });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Install and restart", exact: true })
    .click();
  await expect(dialog).toContainText("The signed update could not be installed.");
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_UPDATER_QA__.records.some(
        (record: any) => record.action === "relaunch",
      ),
    ),
  ).toBe(false);
});

test("Settings reports when the installed version is current", async ({
  page,
}) => {
  await desktopFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Account & appearance" });
  await expect(settings).toContainText("Version 2.0.0");
  await expect(settings).toContainText("You're up to date.");
  await expect(
    settings.getByRole("button", { name: "Check for updates", exact: true }),
  ).toBeEnabled();
});

test("a failed manual check stays visible in Settings and can be retried", async ({
  page,
}) => {
  await desktopFixture(page, { updateError: "GitHub is unavailable." });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Account & appearance" });
  await expect(settings).toContainText("GitHub is unavailable.");
  await settings
    .getByRole("button", { name: "Check for updates", exact: true })
    .click();
  await expect(settings).toContainText("GitHub is unavailable.");
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_UPDATER_QA__.records.filter(
        (record: any) => record.action === "check",
      ).length,
    ),
  ).toBe(2);
});

test("Windows portable builds link to the portable asset and never run NSIS", async ({
  page,
}) => {
  await desktopFixture(page, {
    update: { version: "2.0.1" },
    portable: true,
  });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Close the app before replacing it.");
  await expect(dialog).toContainText(
    "Keep the files beside the executable to retain your settings.",
  );
  await dialog
    .getByRole("button", { name: "Download portable update", exact: true })
    .click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as any).__TRAINS_UPDATER_QA__.records.find(
          (record: any) => record.action === "openUrl",
        ),
      ),
    )
    .toEqual({ action: "openUrl", url: portableAsset });
  expect(
    await page.evaluate(() =>
      (window as any).__TRAINS_UPDATER_QA__.records.some(
        (record: any) => record.action === "install",
      ),
    ),
  ).toBe(false);
});
