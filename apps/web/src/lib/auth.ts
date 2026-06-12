import { auth as clerkAuth } from "@clerk/nextjs/server";

export async function getServerAuth(): Promise<{
  userId: string | null;
  getToken?: () => Promise<string | null>;
}> {
  if (process.env.DISABLE_CLERK_AUTH === "1") {
    return {
      userId: `e2e-${process.env.E2E_TEST_USER_ID ?? "00000000-0000-0000-0000-000000000001"}`,
      getToken: async () => "e2e-test-token",
    };
  }
  const session = await clerkAuth();
  return {
    userId: session.userId,
    getToken: session.getToken ? async () => session.getToken() : undefined,
  };
}
