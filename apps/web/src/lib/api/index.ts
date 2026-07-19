import { getRuntimeMode } from "@/api/client";
import * as live from "./endpoints";
import * as demo from "./demo/adapter";

const demoApi = { ...live, ...demo };

export const api = new Proxy(demoApi, {
  get(_target, property) {
    const adapter = getRuntimeMode() === "demo" ? demoApi : live;
    return Reflect.get(adapter, property);
  },
});

export * from "./types";
export { DEMO_JOB_ID } from "./demo/fixtures";
