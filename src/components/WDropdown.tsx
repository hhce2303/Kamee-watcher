import "./primitives.css";

export interface WDropdownOption {
  value: string;
  label: string;
}

interface WDropdownProps {
  options: WDropdownOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export default function WDropdown({ options, value, onChange, disabled }: WDropdownProps) {
  return (
    <select
      className="w-dropdown"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
