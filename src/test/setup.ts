import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { resetTauriMocks } from "./tauriMocks";

// Global fakes for the Tauri boundary — see tauriMocks.ts. Every test file
// gets these transparently; use emitFake()/invoke from "../test/tauriMocks"
// to simulate backend behavior without a real Tauri runtime.
vi.mock("@tauri-apps/api/core", () => import("./tauriMocks"));
vi.mock("@tauri-apps/api/event", () => import("./tauriMocks"));

afterEach(() => {
  resetTauriMocks();
  // Without this, a component left mounted from a prior test stays subscribed
  // to global stores (e.g. useAppStore) — a later test's setState() call then
  // re-renders that leftover instance too, so its DOM ends up reflecting the
  // *next* test's state instead of its own.
  cleanup();
});
