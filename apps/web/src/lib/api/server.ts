import { getServerAuth } from "@/lib/auth";
import { createAPI } from "./core";

export const apiServer = createAPI(async () => {
  const session = await getServerAuth();
  return session.getToken?.() ?? null;
});
