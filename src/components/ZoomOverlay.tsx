interface ZoomOverlayProps {
  zoom: number;
  onReset: () => void;
}

/** Zoom badge + reset button overlaid on a video frame — presentational,
 * no IPC. Badge only shows once zoomed; reset button is always available. */
export default function ZoomOverlay({ zoom, onReset }: ZoomOverlayProps) {
  const isZoomed = zoom > 1.001;
  return (
    <>
      {isZoomed && (
        <div style={badgeStyle}>ZOOM {Math.round(zoom * 100)}%  ·  arrastra para mover</div>
      )}
      <button
        type="button"
        onClick={onReset}
        onPointerDown={(e) => e.stopPropagation()}
        title="Restablecer zoom de imagen"
        aria-label="Restablecer zoom de imagen"
        style={resetBtnStyle}
      >
        ⟲
      </button>
    </>
  );
}

const badgeStyle = {
  position: "absolute",
  top: 12,
  left: "50%",
  transform: "translateX(-50%)",
  height: 22,
  padding: "0 10px",
  borderRadius: "var(--r-sm)",
  background: "rgba(0, 0, 0, 0.6)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  display: "flex",
  alignItems: "center",
  pointerEvents: "none",
} as const;

const resetBtnStyle = {
  position: "absolute",
  top: 12,
  right: 12,
  width: 26,
  height: 26,
  borderRadius: "var(--r-sm)",
  border: "1px solid rgba(255, 255, 255, 0.15)",
  background: "rgba(0, 0, 0, 0.6)",
  color: "var(--text-primary)",
  fontSize: 14,
  cursor: "pointer",
} as const;
