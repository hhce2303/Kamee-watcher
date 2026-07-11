import { useEffect, useState, useRef } from "react";
import type { MonitorDTO } from "../../types/dto";
import MonitorTile from "./MonitorTile";

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
}

type LayoutState = Record<string, Rect>;

/**
 * A freeform workspace that allows dragging and resizing monitor previews.
 * Fully responsive using percentage positioning.
 * Implement custom pointer events to drag and resize cleanly.
 */
export default function DraggableWorkspace({
  monitors,
  isRecording,
}: {
  monitors: MonitorDTO[];
  isRecording: boolean;
}) {
  const [layout, setLayout] = useState<LayoutState>(() => {
    try {
      const saved = localStorage.getItem("watcher_monitor_layout_v5");
      if (saved) return JSON.parse(saved);
    } catch {}
    return {};
  });

  const containerRef = useRef<HTMLDivElement>(null);
  
  // Interaction state
  const [action, setAction] = useState<"drag" | "resize" | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const dragStart = useRef({ pointerX: 0, pointerY: 0, startX: 0, startY: 0, startW: 0, startH: 0 });

  // Initialize missing monitors
  useEffect(() => {
    let changed = false;
    const newLayout = { ...layout };
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

    if (changed) {
      setLayout(newLayout);
    }
  }, [monitors]);

  // Save to local storage
  useEffect(() => {
    localStorage.setItem("watcher_monitor_layout_v5", JSON.stringify(layout));
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
      startH: rect.h
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
      startH: rect.h
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

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1,
        position: "relative",
        background: "var(--bg-elevated)",
        borderRadius: "var(--r-md)",
        border: "1px solid var(--border-base)",
        overflow: "hidden", // prevents items falling outside visually
      }}
    >
      {monitors.map((m) => {
        const rect = layout[m.fingerprint];
        if (!rect) return null;

        const isActive = activeId === m.fingerprint;

        return (
          <div
            key={m.fingerprint}
            onPointerDown={(e) => handleDragStart(e, m.fingerprint)}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            style={{
              position: "absolute",
              left: `${rect.x}%`,
              top: `${rect.y}%`,
              width: `${rect.w}%`,
              height: `${rect.h}%`,
              zIndex: rect.z,
              boxShadow: isActive ? "0 12px 40px rgba(0,0,0,0.4)" : "0 4px 12px rgba(0,0,0,0.3)",
              cursor: action === "drag" && isActive ? "grabbing" : "grab",
              transition: action && isActive ? "none" : "box-shadow 0.2s, left 0.1s, top 0.1s, width 0.1s, height 0.1s",
              border: `1px solid ${m.selected ? "var(--accent-monitor)" : "var(--border-base)"}`,
              borderRadius: "var(--r-md)",
              background: "var(--bg-base)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Inner wrapper prevents pointer events on image so we can drag the whole tile */}
            <div style={{ pointerEvents: "none", flex: 1, position: "relative", overflow: "hidden" }}>
              <MonitorTile monitor={m} isRecording={isRecording} fillContainer />
            </div>
            
            {/* Custom UI Resize Handle */}
            <div
              className="resize-handle"
              onPointerDown={(e) => handleResizeStart(e, m.fingerprint)}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              style={{
                position: 'absolute',
                right: 0,
                bottom: 0,
                width: 20,
                height: 20,
                cursor: 'nwse-resize',
                zIndex: 10,
                background: 'linear-gradient(135deg, transparent 50%, rgba(200,200,200,0.15) 50%)'
              }}
            />
          </div>
        );
      })}
    </div>
  );
}