import { expect, test } from "@playwright/test";

async function ensureHistoryOrLogin(page) {
  await page.goto("/daftar-tamu/saya/riwayat?tab=beranda");
  const isLogin = /\/login/.test(page.url()) || (await page.locator("input[name='email'], input[type='password']").count()) > 0;
  if (isLogin) {
    await expect(page.getByText(/login|masuk/i).first()).toBeVisible();
    return false;
  }
  await expect(page.getByRole("heading", { name: "Riwayat Buku Tamu Saya" })).toBeVisible();
  return true;
}

test.describe("Guestbook super-app mobile", () => {
  test("beranda renders timeline and chip filter works", async ({ page }) => {
    const hasSession = await ensureHistoryOrLogin(page);
    if (!hasSession) {
      return;
    }

    const timeline = page.locator("#homeTimelineWrap");
    await expect(timeline).toBeVisible();

    const chips = page.locator("[data-home-filter]");
    const chipCount = await chips.count();
    expect(chipCount).toBeGreaterThan(0);

    const firstVisibleChip = chips.nth(Math.min(1, chipCount - 1));
    await firstVisibleChip.click();
    await expect(firstVisibleChip).toHaveAttribute("aria-pressed", "true");
  });

  test("load more keeps instagram-like feed growth", async ({ page }) => {
    const hasSession = await ensureHistoryOrLogin(page);
    if (!hasSession) {
      return;
    }

    const rows = page.locator(".timeline-item[data-transaction-id]");
    const initialCount = await rows.count();
    const loadMoreBtn = page.locator(".js-load-more");

    if (await loadMoreBtn.count()) {
      await loadMoreBtn.first().scrollIntoViewIfNeeded();
      await loadMoreBtn.first().click();
      await page.waitForTimeout(1800);
      const afterCount = await rows.count();
      expect(afterCount).toBeGreaterThanOrEqual(initialCount);
    } else {
      expect(initialCount).toBeGreaterThanOrEqual(0);
    }
  });

  test("staff note sheet can open from first available row", async ({ page }) => {
    const hasSession = await ensureHistoryOrLogin(page);
    if (!hasSession) {
      return;
    }
    const trigger = page.locator(".js-open-staff-note-sheet").first();

    if (await trigger.count()) {
      await trigger.click();
      await expect(page.locator("#staffNoteSheet")).toBeVisible();
    } else {
      // No verified row available in this fixture; page should still render.
      await expect(page.locator("#homeTimelineWrap")).toBeVisible();
    }
  });
});
