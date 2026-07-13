import { useDraggableLayout } from "../../hooks/useDraggableLayout";
import type { MonitorDTO } from "../../types/dto";
import MonitorTile from "./MonitorTile";

/**
 * A freeform workspace that allows dragging and resizing monitor previews.
 * Fully responsive using percentage positioning. Positioning/persistence
 * logic lives in useDraggableLayout — this component is render-only.
 */
export default function DraggableWorkspace({
  monitors,
  isRecording,
}: {
  monitors: MonitorDTO[];
  isRecording: boolean;
}) {
  const {
    containerRef,
    layout,
    action,
    activeId,
    handleDragStart,
    handleResizeStart,
    handlePointerMove,
    handlePointerUp,
    handleTileKeyDown,
  } = useDraggableLayout(monitors);

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

        // "group" is the most semantically honest role for a movable/resizable
        // panel (there's no ARIA widget role for 2D drag+resize); tabIndex +
        // onKeyDown below are real keyboard support (arrows move, Shift+arrows
        // resize), not a decorative role/interaction mismatch.
        /* eslint-disable jsx-a11y/no-noninteractive-tabindex, jsx-a11y/no-noninteractive-element-interactions -- see comment above */
        return (
          <div
            key={m.fingerprint}
            role="group"
            aria-label={`Vista previa de ${m.name} — flechas para mover, Shift+flechas para redimensionar`}
            tabIndex={0}
            onPointerDown={(e) => handleDragStart(e, m.fingerprint)}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onKeyDown={(e) => handleTileKeyDown(e, m.fingerprint)}
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

            {/* Custom UI Resize Handle — pointer-only affordance; Shift+arrow
                keys on the tile itself (role="group" above) cover the
                keyboard-equivalent resize, so this stays out of the a11y tree. */}
            <div
              className="resize-handle"
              aria-hidden="true"
              onPointerDown={(e) => handleResizeStart(e, m.fingerprint)}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              style={{
                position: "absolute",
                right: 0,
                bottom: 0,
                width: 20,
                height: 20,
                cursor: "nwse-resize",
                zIndex: 10,
                background: "linear-gradient(135deg, transparent 50%, rgba(200,200,200,0.15) 50%)",
              }}
            />
          </div>
          /* eslint-enable jsx-a11y/no-noninteractive-tabindex, jsx-a11y/no-noninteractive-element-interactions */
        );
      })}
    </div>
  );
}
