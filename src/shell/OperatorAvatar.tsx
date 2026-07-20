interface OperatorAvatarProps {
  initials: string;
  tone?: string;
  size?: number;
}

/** Monogram tile — port of qml/OperatorAvatar.qml. */
export default function OperatorAvatar({ initials, tone = "var(--accent-primary)", size = 32 }: OperatorAvatarProps) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: Math.max(3, Math.round(size / 4)),
        background: `color-mix(in srgb, ${tone} 16%, transparent)`,
        border: `1px solid color-mix(in srgb, ${tone} 32%, transparent)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: tone,
        fontFamily: "var(--font-mono)",
        fontSize: Math.max(9, Math.round(size * 0.34)),
        fontWeight: 700,
        letterSpacing: "0.3px",
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}
