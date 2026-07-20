import { useEffect, useRef, useState } from "react";
import type { MonitorDTO } from "../types/dto";

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
}

type LayoutState = Record<string, Rect>;

const STORAGE_KEY = "watcher_monitor_layout_v5";
const KEY_STEP = 2; // percent per key press — mirrors the pointer drag granularity

/**
 * Freeform, percentage-based drag/resize layout for monitor preview tiles.
 * Persists to localStorage and provides both pointer and keyboard (arrows to
 * move, Shift+arrows to resize) interaction — extracted from
 * DraggableWorkspace so the positioning/persistence logic is testable and
 * readable independently of the render tree.
 */
export function useDraggableLayout(monitors: MonitorDTO[]) {
  const [layout, setLayout] = useState<LayoutState>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      // Corrupt or missing saved layout — fall through to the default {}.
    }
    return {};
  });

  const containerRef = useRef<HTMLDivElement>(null);

  // Interaction state
  const [action, setAction] = useState<"drag" | "resize" | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const dragStart = useRef({ pointerX: 0, pointerY: 0, startX: 0, startY: 0, startW: 0, startH: 0 });

  // Initialize missing monitors. Reads the previous layout via the setState
  // functional form (not the `layout` closure variable) so this effect only
  // needs to depend on `monitors` — avoids re-running on every drag/resize.
  useEffect(() => {
    setLayout((prev) => {
      let changed = false;
      const newLayout = { ...prev };
      const PADDING_X = 2; // 2% spacing
      const PADDING_Y = 2; // 2% spacing
      const defaultW = 46; // 46% width
      const defaultH = 44; // 44% height

      for (let i = 0; i < monitors.length; i++) {
        const m = monitors[i];
        if (!newLayout[m.fingerprint]) {
          changed = true;
          // Arrange in a simple grid to avoid overlap (2 columns)
          const col = i % 2;
          const row = Math.floor(i / 2);

          newLayout[m.fingerprint] = {
            x: PADDING_X + col * (defaultW + PADDING_X),
            y: PADDING_Y + row * (defaultH + PADDING_Y),
            w: defaultW,
            h: defaultH,
            z: i + 1,
          };
        }
      }

      return changed ? newLayout : prev;
    });
  }, [monitors]);

  // Save to local storage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

  function bringToFront(id: string) {
    setLayout((prev) => {
      if (!prev[id]) return prev;
      const maxZ = Math.max(0, ...Object.values(prev).map((r) => r.z));
      if (prev[id].z === maxZ) return prev;
      return { ...prev, [id]: { ...prev[id], z: maxZ + 1 } };
    });
  }

  // --- Handlers for dragging the whole tile ---
  function handleDragStart(e: React.PointerEvent, id: string) {
    if ((e.target as HTMLElement).closest(".resize-handle")) return; // handled separately
    e.preventDefault();
    bringToFront(id);
    setAction("drag");
    setActiveId(id);
    const rect = layout[id];
    dragStart.current = {
      pointerX: e.clientX,
      pointerY: e.clientY,
      startX: rect.x,
      startY: rect.y,
      startW: rect.w,
      startH: rect.h,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  // --- Handlers for resizing from the bottom-right corner ---
  function handleResizeStart(e: React.PointerEvent, id: string) {
    e.stopPropagation(); // prevent triggering drag
    e.preventDefault();
    bringToFront(id);
    setAction("resize");
    setActiveId(id);
    const rect = layout[id];
    dragStart.current = {
      pointerX: e.clientX,
      pointerY: e.clientY,
      startX: rect.x,
      startY: rect.y,
      startW: rect.w,
      startH: rect.h,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  // --- Unified global move/up handlers per tile ---
  function handlePointerMove(e: React.PointerEvent) {
    if (!action || !activeId || !containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    if (containerRect.width === 0 || containerRect.height === 0) return;

    const dxPercent = ((e.clientX - dragStart.current.pointerX) / containerRect.width) * 100;
    const dyPercent = ((e.clientY - dragStart.current.pointerY) / containerRect.height) * 100;

    setLayout((prev) => {
      const current = prev[activeId];
      if (!current) return prev;

      if (action === "drag") {
        return {
          ...prev,
          [activeId]: {
            ...current,
            // clamp between 0% and 100% boundary
            x: Math.max(0, Math.min(100 - current.w, dragStart.current.startX + dxPercent)),
            y: Math.max(0, Math.min(100 - current.h, dragStart.current.startY + dyPercent)),
          },
        };
      } else if (action === "resize") {
        return {
          ...prev,
          [activeId]: {
            ...current,
            // minimum 10% width/height, max available space
            w: Math.max(10, Math.min(100 - current.x, dragStart.current.startW + dxPercent)),
            h: Math.max(10, Math.min(100 - current.y, dragStart.current.startH + dyPercent)),
          },
        };
      }
      return prev;
    });
  }

  function handlePointerUp(e: React.PointerEvent) {
    if (action) {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      setAction(null);
      setActiveId(null);
    }
  }

  // --- Keyboard equivalent for drag (arrows) and resize (Shift+arrows) ---
  function handleTileKeyDown(e: React.KeyboardEvent, id: string) {
    const direction: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    const delta = direction[e.key];
    if (!delta) return;
    e.preventDefault();
    bringToFront(id);
    const [dx, dy] = delta;
    setLayout((prev) => {
      const current = prev[id];
      if (!current) return prev;
      if (e.shiftKey) {
        return {
          ...prev,
          [id]: {
            ...current,
            w: Math.max(10, Math.min(100 - current.x, current.w + dx * KEY_STEP)),
            h: Math.max(10, Math.min(100 - current.y, current.h + dy * KEY_STEP)),
          },
        };
      }
      return {
        ...prev,
        [id]: {
          ...current,
          x: Math.max(0, Math.min(100 - current.w, current.x + dx * KEY_STEP)),
          y: Math.max(0, Math.min(100 - current.h, current.y + dy * KEY_STEP)),
        },
      };
    });
  }

  return {
    containerRef,
    layout,
    action,
    activeId,
    handleDragStart,
    handleResizeStart,
    handlePointerMove,
    handlePointerUp,
    handleTileKeyDown,
  };
}
