import { useEffect, type ReactNode } from "react";
import "./primitives.css";

interface ModalProps {
  onClose?: () => void;
  children: ReactNode;
}

/** Shared dialog scaffold — click on the overlay or Escape (not the panel) closes it. */
export default function Modal({ onClose, children }: ModalProps) {
  useEffect(() => {
    if (!onClose) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    // role="presentation": this backdrop is decorative, not an interactive
    // control — the keyboard-equivalent close action is the Escape listener
    // above, not a key handler on this element.
    <div
      className="w-modal-overlay"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div className="w-modal" role="dialog" aria-modal="true">
        {children}
      </div>
    </div>
  );
}
