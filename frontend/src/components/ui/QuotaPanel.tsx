import { useEffect } from "react";
import { useQuotaStore } from "../../stores/quotaStore";
import { Activity, Database, Zap, Infinity as InfinityIcon } from "lucide-react";

interface BarProps {
  label: string;
  used: number;
  limit: number;
  icon?: React.ReactNode;
}

function Bar({ label, used, limit, icon }: BarProps) {
  const isUnlimited = limit <= 0;
  const pct = isUnlimited ? 0 : Math.min((used / limit) * 100, 100);
  const isHigh = pct >= 80;
  const isExhausted = pct >= 100;

  const barColor = isExhausted
    ? "bg-error"
    : isHigh
      ? "bg-warning"
      : "bg-primary-500";

  const textColor = isExhausted
    ? "text-error"
    : isHigh
      ? "text-warning"
      : "text-text-muted";

  return (
    <div className="space-y-1.5 py-1">
      <div className="flex justify-between items-end text-xs">
        <div className="flex items-center gap-1.5 text-text-primary font-medium">
          {icon}
          <span>{label}</span>
        </div>
        <span className={textColor}>
          <span className="font-bold">{used}</span>
          <span className="opacity-70 mx-0.5">/</span>
          {isUnlimited ? <InfinityIcon className="w-3.5 h-3.5 inline-block" /> : limit}
        </span>
      </div>
      {!isUnlimited && (
        <div className="h-2 w-full bg-bg-tertiary rounded-full overflow-hidden shadow-inner relative">
          <div
            className={`absolute top-0 left-0 h-full rounded-full transition-all duration-1000 ease-in-out ${barColor} ${isExhausted ? "animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.5)]" : ""
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
    <div className="px-3 py-3 rounded-lg bg-bg-primary border border-border space-y-3 shadow-sm relative overflow-hidden mx-1 mt-auto">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-3.5 h-3.5 text-primary-400" />
        <p className="text-xs font-semibold uppercase tracking-wider text-text-primary">
          Daily Quota
        </p>
      </div>

      <div className="space-y-2 relative z-10">
        <Bar
          label="Queries"
          used={quota.queries.used}
          limit={quota.queries.limit}
          icon={<Activity className="w-3.5 h-3.5 text-primary-400" />}
        />
        <Bar
          label="Prescriptions"
          used={quota.prescriptions.used}
          limit={quota.prescriptions.limit}
          icon={<Database className="w-3.5 h-3.5 text-primary-400" />}
        />
      </div>
    </div>
  );
}