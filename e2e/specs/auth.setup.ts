import { test as setup } from "@playwright/test";
import { signIn } from "../helpers/auth";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  if (process.env.DISABLE_CLERK_AUTH === "1") {
    // Auth bypass: server-side middleware injects the test user;
    // no Clerk sign-in state is required.
    await page.context().storageState({ path: authFile });
    return;
  }
  await signIn(page);
  await page.context().storageState({ path: authFile });
});
