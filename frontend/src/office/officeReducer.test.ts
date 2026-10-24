import { describe, expect, it } from "vitest";
import type { Role, ServerEvent } from "../api/types";
import { initialOfficeState, officeReducer, type OfficeAction, type OfficeState } from "./officeReducer";

const role = (id: string, name: string): Role => ({ id, name, title: "", reports_to: null, voice: "default" });
const ROLES = [role("engineer", "Dwight Schrute"), role("sales_lead", "Jim Halpert")];
const run = (...actions: OfficeAction[]): OfficeState => actions.reduce(officeReducer, initialOfficeState(ROLES));

const completed = (task_id = "DM-111", from_role = "engineer", title = "Fix bulk discount"): ServerEvent => ({
  type: "task.completed",
  task_id,
  from_role,
  title,
  summary: "Fixed.",
});
const ping = (to_role: string | null, from_role = "engineer"): ServerEvent => ({
  type: "ping",
  to_role,
  from_role,
  task_id: "DM-111",
  text: "Fixed.",
});

describe("officeReducer", () => {
  it('completed adds bang and toast text "DWIGHT: Fix bulk discount is done!"', () => {
    const s = run(completed());
    expect(s.bang).toEqual({ engineer: ["DM-111"] });
    expect(s.toasts).toEqual([{ id: "DM-111", text: "DWIGHT: Fix bulk discount is done!", task_id: "DM-111" }]);
  });

  it("the same completion twice adds nothing new", () => {
    const s = run(completed(), completed());
    expect(s.bang.engineer).toEqual(["DM-111"]);
    expect(s.toasts).toHaveLength(1);
  });

  it("null ping rings sender", () => {
    expect(run(ping(null)).ringing).toEqual({ engineer: true });
  });

  it("a ping delivered inside a call doesn't ring", () => {
    const s = run(ping("sales_lead"));
    expect(s.ringing).toEqual({});
  });

  it("called clears bang and ringing", () => {
    const s = run(completed(), ping(null), completed("DM-112", "sales_lead", "Pitch deck"), { type: "called", roleId: "engineer" });
    expect(s.bang).toEqual({ sales_lead: ["DM-112"] });
    expect(s.ringing).toEqual({});
    expect(s.toasts).toHaveLength(2); // toasts stay until opened or dismissed
  });

  it("opened_result clears", () => {
    const s = run(completed(), completed("DM-112"), ping(null), { type: "opened_result", task_id: "DM-111" });
    expect(s.bang).toEqual({ engineer: ["DM-112"] });
    expect(s.toasts.map((t) => t.task_id)).toEqual(["DM-112"]);

    const all = officeReducer(s, { type: "opened_result", task_id: "DM-112" });
    expect(all.bang).toEqual({});
    expect(all.ringing).toEqual({}); // nothing left to tell you about
  });

  it("agent.status tracks idle / working / on_call", () => {
    const s = run(
      { type: "agent.status", role: "engineer", state: "working" },
      { type: "agent.status", role: "sales_lead", state: "on_call" },
      { type: "agent.status", role: "sales_lead", state: "idle" },
    );
    expect(s.agents).toEqual({ engineer: "working", sales_lead: "idle" });
  });

  it("event for unknown role adds entry without throwing", () => {
    const s = run(
      completed("DM-200", "receptionist", "Answer phones"),
      ping(null, "receptionist"),
      { type: "agent.status", role: "receptionist", state: "working" },
    );
    expect(s.bang.receptionist).toEqual(["DM-200"]);
    expect(s.ringing.receptionist).toBe(true);
    expect(s.agents.receptionist).toBe("working");
    expect(s.toasts[0].text).toBe("RECEPTIONIST: Answer phones is done!");
  });

  it("roles updates names for later toasts", () => {
    const s = run({ type: "roles", roles: [...ROLES, role("receptionist", "Pam Beesly")] }, completed("DM-200", "receptionist", "Answer phones"));
    expect(s.toasts[0].text).toBe("PAM: Answer phones is done!");
  });

  it("dismiss_toast removes only the toast", () => {
    const s = run(completed(), { type: "dismiss_toast", id: "DM-111" });
    expect(s.toasts).toEqual([]);
    expect(s.bang.engineer).toEqual(["DM-111"]);
  });

  it("unrelated events return the same state", () => {
    const s = run();
    expect(officeReducer(s, { type: "resync" })).toBe(s);
    expect(officeReducer(s, { type: "task.updated", task_id: "x", status: "todo", assignee_role: null, title: "x" })).toBe(s);
    expect(officeReducer(s, { type: "called", roleId: "nobody" })).toBe(s);
  });
});
