import "./primitives.css";

export interface WSegOption<T> {
  value: T;
  label: string;
}

interface WSegProps<T> {
  options: WSegOption<T>[];
  value: T;
  onSelect: (value: T) => void;
}

export default function WSeg<T extends string | number>({ options, value, onSelect }: WSegProps<T>) {
  return (
    <div className="w-seg" role="radiogroup">
      {options.map((opt) => (
        <button
          key={String(opt.value)}
          type="button"
          role="radio"
          aria-checked={opt.value === value}
          className={`w-seg__item ${opt.value === value ? "active" : ""}`}
          onClick={() => onSelect(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
