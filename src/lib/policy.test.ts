import { describe, expect, it } from "vitest";
import { isTabVisible, policyFor } from "./policy";

describe("policyFor", () => {
  it("operator can only see tab 0 and cannot close/minimize/exit", () => {
    const p = policyFor("operator");
    expect(p.visibleTabs).toEqual([0]);
    expect(p.canCloseWindow).toBe(false);
    expect(p.canMinimizeWindow).toBe(false);
    expect(p.canExitFromTray).toBe(false);
    expect(p.recordsOnLaunchForced).toBe(true);
    expect(p.canChangeRole).toBe(false);
  });

  it("supervisor can only see tab 1 and does not record", () => {
    const p = policyFor("supervisor");
    expect(p.visibleTabs).toEqual([1]);
    expect(p.records).toBe(false);
    expect(p.canChangeRole).toBe(false);
  });

  it("it sees all tabs and can change role", () => {
    const p = policyFor("it");
    expect(p.visibleTabs).toEqual([]);
    expect(p.canChangeRole).toBe(true);
    expect(p.records).toBe(true);
    expect(p.recordsOnLaunchForced).toBe(false);
  });

  it("unknown/empty role falls back to the unconfigured policy (inert, can change role)", () => {
    const empty = policyFor("");
    const bogus = policyFor("not-a-role");
    expect(empty).toEqual(bogus);
    expect(empty.records).toBe(false);
    expect(empty.canChangeRole).toBe(true);
  });
});

describe("isTabVisible", () => {
  it("an empty visibleTabs list means every tab is visible", () => {
    const p = policyFor("it");
    expect(isTabVisible(p, 0)).toBe(true);
    expect(isTabVisible(p, 3)).toBe(true);
  });

  it("a non-empty visibleTabs list restricts to those indices", () => {
    const p = policyFor("operator");
    expect(isTabVisible(p, 0)).toBe(true);
    expect(isTabVisible(p, 1)).toBe(false);
  });
});
