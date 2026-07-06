/**
 * Per-role capability policy — TS mirror of project/app/core/policy.py.
 *
 * Keep in exact sync with the Python source; that module is the single
 * source of truth (Python also drives `enforce_role`, the tray, and role-
 * change authorization server-side, so this copy only needs to answer UI
 * layout/gating questions — the backend enforces the real rules).
 */

export interface RolePolicy {
  canCloseWindow: boolean;
  canMinimizeWindow: boolean;
  canExitFromTray: boolean;
  records: boolean;
  recordsOnLaunchForced: boolean;
  canStopRecording: boolean;
  canOpenSettings: boolean;
  /** Empty array means "all tabs visible". */
  visibleTabs: number[];
  canChangeRole: boolean;
  recordingIndicatorLocked: boolean;
  watchdogEnabled: boolean;
}

const OPERATOR: RolePolicy = {
  canCloseWindow: false,
  canMinimizeWindow: false,
  canExitFromTray: false,
  records: true,
  recordsOnLaunchForced: true,
  canStopRecording: false,
  canOpenSettings: false,
  visibleTabs: [0],
  canChangeRole: false,
  recordingIndicatorLocked: true,
  watchdogEnabled: true,
};

const SUPERVISOR: RolePolicy = {
  canCloseWindow: true,
  canMinimizeWindow: true,
  canExitFromTray: true,
  records: false,
  recordsOnLaunchForced: false,
  canStopRecording: true,
  canOpenSettings: true,
  visibleTabs: [1],
  canChangeRole: false,
  recordingIndicatorLocked: false,
  watchdogEnabled: false,
};

const IT: RolePolicy = {
  canCloseWindow: true,
  canMinimizeWindow: true,
  canExitFromTray: true,
  records: true,
  recordsOnLaunchForced: false,
  canStopRecording: true,
  canOpenSettings: true,
  visibleTabs: [], // all tabs — the full-screen IT editor is handled separately
  canChangeRole: true,
  recordingIndicatorLocked: false,
  watchdogEnabled: false,
};

// Unconfigured machine (role === ""): inert until the role wizard runs.
const UNCONFIGURED: RolePolicy = {
  canCloseWindow: true,
  canMinimizeWindow: true,
  canExitFromTray: true,
  records: false,
  recordsOnLaunchForced: false,
  canStopRecording: true,
  canOpenSettings: true,
  visibleTabs: [],
  canChangeRole: true,
  recordingIndicatorLocked: false,
  watchdogEnabled: false,
};

const BY_ROLE: Record<string, RolePolicy> = {
  operator: OPERATOR,
  supervisor: SUPERVISOR,
  it: IT,
};

export function policyFor(role: string): RolePolicy {
  return BY_ROLE[role] ?? UNCONFIGURED;
}

/** True if `tabIndex` should render for this policy ([] visibleTabs = show all). */
export function isTabVisible(policy: RolePolicy, tabIndex: number): boolean {
  return policy.visibleTabs.length === 0 || policy.visibleTabs.includes(tabIndex);
}
