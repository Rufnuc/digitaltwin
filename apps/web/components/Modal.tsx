"use client";
import type { ReactNode } from "react";

/** A roomy, scrollable, centered popup. Sits above row view-drawers (z-50) and
 * other in-drawer modals (z-70). */
export function Modal({
  title,
  onClose,
  children,
  size = "lg",
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  size?: "md" | "lg" | "xl";
}) {
  const max = size === "xl" ? "max-w-3xl" : size === "lg" ? "max-w-2xl" : "max-w-md";
  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:items-center"
      onMouseDown={onClose}
    >
      <div
        className={`my-auto w-full ${max} max-h-[90vh] overflow-y-auto rounded-xl border border-line bg-paper p-5 shadow-2xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="ml-auto text-muted hover:text-ink">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
