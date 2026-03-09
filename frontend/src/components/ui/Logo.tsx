import { Pill } from "lucide-react";

export function Logo({ size = 64, className = "" }: { size?: number; className?: string }) {
  const iconSize = Math.round(size * 0.55);
  return (
    <div
      className={`flex items-center justify-center bg-emerald-500 ${className}`}
      style={{ width: size, height: size, borderRadius: size * 0.22 }}
    >
      <Pill className="text-white" style={{ width: iconSize, height: iconSize }} />
    </div>
  );
}
