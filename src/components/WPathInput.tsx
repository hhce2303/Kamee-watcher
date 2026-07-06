import "./primitives.css";

interface WPathInputProps {
  path: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
}

export default function WPathInput({ path, onPathChange, onBrowse }: WPathInputProps) {
  return (
    <div className="w-path-input">
      <span className="w-path-input__icon">📁</span>
      <input
        className="w-path-input__field"
        value={path}
        onChange={(e) => onPathChange(e.target.value)}
      />
      <button type="button" className="w-path-input__browse" onClick={onBrowse}>
        EXAMINAR
      </button>
    </div>
  );
}
