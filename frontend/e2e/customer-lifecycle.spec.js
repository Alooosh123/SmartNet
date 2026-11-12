import { test, expect } from "@playwright/test";

const username = "e2e-portal-customer";
const customerPassword = "SmartNet-customer-password-2026!";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGMUqQhgwAaYsIoOWgkAsPQA7HvjDaMAAAAASUVORK5CYII=",
  "base64",
);

test("customer registration -> manual review -> activation -> portal -> chat -> card PDF", async ({ browser, page }) => {
  // Customer creates a registration and uploads proof; the receipt must not
  // activate the account or mark payment as verified.
  await page.goto("/");
  await page.getByRole("button", { name: "إنشاء اشتراك عميل جديد" }).click();

  await page.getByLabel("اسم المستخدم").fill(username);
  await page.getByLabel("كلمة المرور").fill(customerPassword);
  await page.getByLabel("الباقة").selectOption("annual");
  await page.getByRole("button", { name: "إنشاء طلب الاشتراك" }).click();

  await expect(page.getByText(/رقم الطلب:/)).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "proof.png",
    mimeType: "image/png",
    buffer: png,
  });
  await expect(page.getByText(/تم رفع الإيصال|بانتظار المراجعة/)).toBeVisible();

  // A separate administrator context checks the receipt and performs the two
  // auditable decisions: verify funds, then activate the subscription.
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  await adminPage.goto("/");
  await adminPage.getByLabel("اسم المستخدم").fill("e2e-admin");
  await adminPage.getByLabel("كلمة المرور").fill("SmartNet-E2E-admin-password-2026!");
  await adminPage.getByRole("button", { name: "تسجيل الدخول" }).click();

  await expect(adminPage.getByRole("heading", { name: "نظرة عامة" })).toBeVisible();
  await adminPage.getByRole("button", { name: "طلبات الاشتراك" }).click();
  const requestRow = adminPage.getByRole("row").filter({ hasText: username });
  await expect(requestRow).toBeVisible();
  await expect(requestRow.getByText("بانتظار الدفع")).toBeVisible();

  adminPage.on("dialog", async dialog => {
    if (dialog.type === "prompt") {
      const prompt = dialog.message();
      if (prompt.includes("USD")) await dialog.accept("100");
      else if (prompt.includes("cash")) await dialog.accept("mobile_wallet");
      else if (prompt.includes("مرجع")) await dialog.accept("E2E-MANUAL-TRANSFER-001");
      else await dialog.accept();
    } else {
      await dialog.accept();
    }
  });
  await requestRow.getByRole("button", { name: "تأكيد وصول المبلغ" }).click();
  await expect(requestRow.getByRole("button", { name: "اعتماد الاشتراك" })).toBeVisible();
  await requestRow.getByRole("button", { name: "اعتماد الاشتراك" }).click();
  await expect(requestRow.getByText("معتمد")).toBeVisible();

  // The original customer registration token can now observe activation.
  await page.getByRole("button", { name: "تحديث حالة الطلب" }).click();
  await expect(page.getByText("تم اعتماد الاشتراك. يمكنك الآن تسجيل الدخول.")).toBeVisible();
  await page.getByRole("button", { name: "العودة لتسجيل الدخول" }).click();

  // Customer signs in and sees only their permitted portal features.
  await page.getByLabel("اسم المستخدم").fill(username);
  await page.getByLabel("كلمة المرور").fill(customerPassword);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await expect(page.getByRole("heading", { name: "مرحباً، " + username })).toBeVisible();
  await expect(page.getByRole("button", { name: "كروت الهوت سبوت" })).toBeVisible();

  // Generate credentials and download the private PDF via the normal portal UI.
  await page.getByRole("button", { name: "كروت الهوت سبوت" }).click();
  await page.getByLabel("عدد الكروت").fill("2");
  await page.getByLabel("Profile").selectOption({ label: "1 Day" });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "توليد وتنزيل PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^smartnet_batch_\d+\.pdf$/);

  // Free-text chat can explain an action, but it must not reboot the router.
  await page.getByRole("button", { name: "المساعد والدعم" }).click();
  await page.getByPlaceholder("اكتب رسالتك هنا...").fill("إعادة تشغيل الراوتر");
  await page.getByRole("button", { name: "إرسال" }).click();
  await expect(page.getByText(/لا أنفذها من رسالة محادثة/)).toBeVisible();

  // A subscriber can request an operation but cannot execute it directly.
  await page.getByRole("button", { name: "حسابي" }).click();
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "إعادة تشغيل الشبكة" }).click();
  await expect(page.getByText(/تم تسجيل طلب إعادة التشغيل/)).toBeVisible();

  // An administrator reviews the request and the demo router receives the approved action.
  await adminPage.getByRole("button", { name: "موافقات الشبكة" }).click();
  const actionRow = adminPage.getByRole("row").filter({ hasText: username });
  await expect(actionRow).toBeVisible();
  await actionRow.getByRole("button", { name: "اعتماد" }).click();
  await expect(actionRow.getByText("executed")).toBeVisible();

  await adminPage.getByRole("button", { name: "المطابقة المالية" }).click();
  await expect(adminPage.getByText("E2E-MANUAL-TRANSFER-001")).toBeVisible();
  await adminPage.getByRole("button", { name: "مراقبة الشبكة" }).click();
  await adminPage.getByRole("button", { name: "جمع قراءة الآن" }).click();
  await expect(adminPage.getByText("قراءة فقط")).toBeVisible();

  await adminContext.close();
});
