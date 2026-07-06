import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { resetTauriMocks } from "./tauriMocks";

// Global fakes for the Tauri boundary — see tauriMocks.ts. Every test file
// gets these transparently; use emitFake()/invoke from "../test/tauriMocks"
// to simulate backend behavior without a real Tauri runtime.
vi.mock("@tauri-apps/api/core", () => import("./tauriMocks"));
vi.mock("@tauri-apps/api/event", () => import("./tauriMocks"));

afterEach(() => {
  resetTauriMocks();
});
