import { isDemoMode } from "@/api/client";
import * as live from "./endpoints";
import * as demo from "./demo/adapter";

export const api = isDemoMode ? { ...live, ...demo } : live;

export { isDemoMode };
export * from "./types";
export { DEMO_JOB_ID } from "./demo/fixtures";
