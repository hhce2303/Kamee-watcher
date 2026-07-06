import type { ReactNode } from "react";
import "./primitives.css";

interface WSettingsRowProps {
  label: string;
  helper?: string;
  vertical?: boolean;
  children: ReactNode;
}

export default function WSettingsRow({ label, helper, vertical, children }: WSettingsRowProps) {
  return (
    <div className={`w-settings-row ${vertical ? "vertical" : ""}`}>
      <div className="w-settings-row__label">
        <span className="w-settings-row__label-text">{label}</span>
        {helper && <span className="w-settings-row__helper">{helper}</span>}
      </div>
      <div className="w-settings-row__control">{children}</div>
    </div>
  );
}
