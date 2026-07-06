interface MarkEventButtonProps {
  onClick: () => void;
  disabled?: boolean;
}

/** MARCAR EVENTO button — port of the control in qml/Main.qml's tab 0. */
export default function MarkEventButton({ onClick, disabled }: MarkEventButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        height: 44,
        padding: "0 28px",
        borderRadius: "var(--r-md)",
        background: "var(--accent-record)",
        border: "none",
        color: "#fff",
        fontFamily: "var(--font-sans)",
        fontSize: 14,
        fontWeight: 700,
        letterSpacing: "0.5px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      ● MARCAR EVENTO
    </button>
  );
}
