import { createGateway } from "./gateway";
import type { Gateway } from "./types";

export const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000";
export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

// The mock gateway lands in C2 (api/mock.ts); until then VITE_MOCK is ignored.
export const gateway: Gateway = createGateway(GATEWAY_URL);
