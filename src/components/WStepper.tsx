import { useEffect, useState } from "react";
import "./primitives.css";

interface WStepperProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
}

export default function WStepper({ value, min = 0, max = 9999, step = 1, unit = "", onChange }: WStepperProps) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const clamp = (v: number) => Math.max(min, Math.min(max, v));

  function commit() {
    const n = Number(text);
    if (!Number.isNaN(n)) onChange(clamp(n));
    else setText(String(value));
  }

  return (
    <div className="w-stepper">
      <button type="button" className="w-stepper__btn" onClick={() => onChange(clamp(value - step))}>
        −
      </button>
      <input
        className="w-stepper__value"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
      {unit && <span className="w-stepper__unit">{unit}</span>}
      <button type="button" className="w-stepper__btn" onClick={() => onChange(clamp(value + step))}>
        +
      </button>
    </div>
  );
}
