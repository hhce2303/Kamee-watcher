import "./primitives.css";

interface WToggleProps {
  checked: boolean;
  onToggle: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

export default function WToggle({ checked, onToggle, disabled, ...aria }: WToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={`w-toggle ${checked ? "checked" : ""}`}
      onClick={() => onToggle(!checked)}
      {...aria}
    >
      <span className="w-toggle__knob" />
    </button>
  );
}
