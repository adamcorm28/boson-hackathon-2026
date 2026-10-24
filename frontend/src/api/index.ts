import { createGateway } from "./gateway";
import { createMockGateway } from "./mock";
import type { Gateway } from "./types";

export const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000";
export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

function pickGateway(): Gateway {
  if (!USE_MOCK) return createGateway(GATEWAY_URL);
  const mock = createMockGateway();
  // Console hooks for manual testing: __mockGateway.simulateUserTurn() (hand-off without a mic),
  // __mockGateway.endActiveCall("idle_timeout"), __mockGateway.resync()
  Object.assign(window, { __mockGateway: mock });
  return mock;
}

export const gateway: Gateway = pickGateway();
