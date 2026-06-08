import { auth } from "@clerk/nextjs/server";
import { createAPI } from "./core";

export const apiServer = createAPI(async () => {
  const session = await auth();
  return session.getToken();
});
