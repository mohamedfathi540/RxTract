import { useEffect } from "react";
import { useQuotaStore } from "../../stores/quotaStore";
import type { QuotaUsage } from "../../api/types";

function Bar({ label, usage }: { label: string; usage: QuotaUsage }) {
  const isUnlimited = usage.limit <= 0;
  const pct = isUnlimited ? 0 : Math.min((usage.used / usage.limit) * 100, 100);
  const isHigh = pct >= 80;
  const isExhausted = pct >= 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-text-muted">{label}</span>
        <span
          className={
            isExhausted
              ? "text-error font-medium"
              : isHigh
                ? "text-warning"
                : "text-text-secondary"
          }
        >
          {isUnlimited
            ? `${usage.used} / ∞`
            : `${usage.used} / ${usage.limit}`}
        </span>
      </div>
      {!isUnlimited && (
        <div className="h-1 rounded-full bg-border overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              isExhausted
                ? "bg-error"
                : isHigh
                  ? "bg-warning"
                  : "bg-primary-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export function QuotaPanel() {
  const { quota, isLoading, fetchQuota } = useQuotaStore();

  useEffect(() => {
    fetchQuota();
    // Refresh every 60 seconds
    const id = setInterval(fetchQuota, 60_000);
    return () => clearInterval(id);
  }, [fetchQuota]);

  if (isLoading && !quota) return null;
  if (!quota) return null;

  return (
    <div className="space-y-2 px-1">
      <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
        Daily Usage
      </p>
      <Bar label="Uploads" usage={quota.uploads} />
      <Bar label="Queries" usage={quota.queries} />
      <Bar label="Prescriptions" usage={quota.prescriptions} />
    </div>
  );
}
