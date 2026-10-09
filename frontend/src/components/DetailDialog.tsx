import { useEffect, useRef } from "react";
import type { Initiative } from "../api/types";
import { DetailBody } from "./DetailBody";

export function DetailDialog({
  initiative,
  onClose,
}: {
  initiative: Initiative;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;

    closeRef.current?.focus();

    const onKey = (e: KeyboardEvent) =>
      e.key === "Escape" && onClose();

    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="overlay"
      onMouseDown={(e) =>
        e.target === e.currentTarget && onClose()
      }
    >
      <div
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-label={initiative.name}
      >
        <button
          ref={closeRef}
          type="button"
          className="dialog-close"
          onClick={onClose}
        >
          Close
        </button>

        <DetailBody initiative={initiative} />
      </div>
    </div>
  );
}