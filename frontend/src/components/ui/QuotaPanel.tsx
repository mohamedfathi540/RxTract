import { useEffect } from "react";
import { useQuotaStore } from "../../stores/quotaStore";
import type { QuotaUsage } from "../../api/types";
import { Zap, Activity, Database } from "lucide-react";

function Bar({ label, icon: Icon, usage }: { label: string; icon: any; usage: QuotaUsage }) {
  const isUnlimited = usage.limit <= 0;

  return (
    <div className="flex items-center justify-between text-[13px] py-1">
      <div className="flex items-center gap-2.5 font-bold text-white tracking-wide drop-shadow-sm">
        <Icon className="w-4 h-4 text-[#4ba2ff] stroke-[2.5]" />
        <span>{label}</span>
      </div>
      <span className="text-gray-300 font-bold text-[12px] tracking-wider font-mono">
        {isUnlimited
          ? `${usage.used} / ∞`
          : `${usage.used} / ${usage.limit}`}
      </span>
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
    <div className="relative rounded-2xl bg-[#1c1c1e] border border-white/5 p-4 overflow-hidden shadow-lg mx-1 mt-auto">
      {/* Background watermark icon */}
      <Zap className="absolute top-1/2 -right-4 -translate-y-1/2 w-32 h-32 text-white/[0.02] stroke-[1] -rotate-12 pointer-events-none" />
      
      <div className="space-y-3 relative z-10">
        <div className="flex items-center gap-2.5 mb-2">
          <Zap className="w-4 h-4 text-[#4ba2ff] fill-transparent stroke-[2.5]" />
          <span className="text-white font-bold tracking-widest text-[13px] uppercase drop-shadow-sm">
            Daily Quota
          </span>
        </div>
        
        <div className="pl-0 space-y-2">
          <Bar label="Queries" icon={Activity} usage={quota.queries} />
          <Bar label="Scrapes" icon={Database} usage={quota.prescriptions} />
        </div>
      </div>
    </div>
  );
}
