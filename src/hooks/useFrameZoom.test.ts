import { act, renderHook } from "@testing-library/react";
import type { PointerEvent, WheelEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { clampZoom, isIdentityZoom, useFrameZoom } from "./useFrameZoom";

function wheelEvent(deltaY: number): WheelEvent {
  return { deltaY, preventDefault: vi.fn() } as unknown as WheelEvent;
}

function pointerEvent(clientX: number, clientY: number, pointerId = 1): PointerEvent {
  return {
    clientX,
    clientY,
    pointerId,
    preventDefault: vi.fn(),
    target: { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn() },
  } as unknown as PointerEvent;
}

describe("clampZoom / isIdentityZoom", () => {
  it("clamps to [1, 6]", () => {
    expect(clampZoom(1, 1 / 1.12)).toBe(1);
    expect(clampZoom(6, 1.12)).toBe(6);
    expect(clampZoom(2, 1.12)).toBeCloseTo(2.24, 5);
  });

  it("treats zoom <= 1.001 as identity", () => {
    expect(isIdentityZoom(1)).toBe(true);
    expect(isIdentityZoom(1.001)).toBe(true);
    expect(isIdentityZoom(1.002)).toBe(false);
  });
});

describe("useFrameZoom", () => {
  it("starts at identity", () => {
    const { result } = renderHook(() => useFrameZoom());
    expect(result.current.zoom).toBe(1);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
    expect(result.current.isZoomed).toBe(false);
  });

  it("zooms in on scroll-up (negative deltaY) and clamps at 6x", () => {
    const { result } = renderHook(() => useFrameZoom());
    act(() => {
      for (let i = 0; i < 40; i++) result.current.handlers.onWheel(wheelEvent(-1));
    });
    expect(result.current.zoom).toBe(6);
    expect(result.current.isZoomed).toBe(true);
  });

  it("zooms back out and snaps to identity", () => {
    const { result } = renderHook(() => useFrameZoom());
    act(() => {
      result.current.handlers.onWheel(wheelEvent(-1));
      result.current.handlers.onWheel(wheelEvent(-1));
    });
    expect(result.current.zoom).toBeGreaterThan(1);

    act(() => {
      for (let i = 0; i < 10; i++) result.current.handlers.onWheel(wheelEvent(1));
    });
    expect(result.current.zoom).toBe(1);
    expect(result.current.panX).toBe(0);
  });

  it("ignores drag while at identity zoom", () => {
    const { result } = renderHook(() => useFrameZoom());
    act(() => {
      result.current.handlers.onPointerDown(pointerEvent(100, 100));
      result.current.handlers.onPointerMove(pointerEvent(150, 120));
    });
    expect(result.current.isDragging).toBe(false);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
  });

  it("pans by unscaled screen-pixel drag delta once zoomed", () => {
    const { result } = renderHook(() => useFrameZoom());
    act(() => {
      result.current.handlers.onWheel(wheelEvent(-1));
    });
    expect(result.current.zoom).toBeGreaterThan(1);

    act(() => {
      result.current.handlers.onPointerDown(pointerEvent(100, 100));
    });
    expect(result.current.isDragging).toBe(true);

    act(() => {
      result.current.handlers.onPointerMove(pointerEvent(150, 80));
    });
    expect(result.current.panX).toBe(50);
    expect(result.current.panY).toBe(-20);

    act(() => {
      result.current.handlers.onPointerUp(pointerEvent(150, 80));
    });
    expect(result.current.isDragging).toBe(false);
  });

  it("reset() snaps zoom and pan back to identity", () => {
    const { result } = renderHook(() => useFrameZoom());
    act(() => {
      result.current.handlers.onWheel(wheelEvent(-1));
    });
    act(() => {
      result.current.handlers.onPointerDown(pointerEvent(0, 0));
    });
    act(() => {
      result.current.handlers.onPointerMove(pointerEvent(40, 40));
    });
    expect(result.current.zoom).toBeGreaterThan(1);
    expect(result.current.panX).toBe(40);
    expect(result.current.panY).toBe(40);

    act(() => result.current.reset());
    expect(result.current.zoom).toBe(1);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
  });

  it("resets when resetKey changes (e.g. switching clips)", () => {
    const { result, rerender } = renderHook(({ key }) => useFrameZoom(key), {
      initialProps: { key: "clip-a" },
    });
    act(() => {
      result.current.handlers.onWheel(wheelEvent(-1));
    });
    expect(result.current.zoom).toBeGreaterThan(1);

    rerender({ key: "clip-b" });
    expect(result.current.zoom).toBe(1);
  });
});
