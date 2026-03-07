export function Logo({ size = 64, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Background circle */}
      <rect width="64" height="64" rx="14" fill="#10B981" />
      {/* Rx text */}
      <text
        x="32"
        y="42"
        textAnchor="middle"
        fontFamily="system-ui, sans-serif"
        fontWeight="bold"
        fontSize="28"
        fill="white"
      >
        Rx
      </text>
    </svg>
  );
}
