import type { ReactNode } from "react";
import "./primitives.css";

interface ModalProps {
  onClose?: () => void;
  children: ReactNode;
}

/** Shared dialog scaffold — click on the overlay (not the panel) closes it. */
export default function Modal({ onClose, children }: ModalProps) {
  return (
    <div
      className="w-modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div className="w-modal">{children}</div>
    </div>
  );
}
