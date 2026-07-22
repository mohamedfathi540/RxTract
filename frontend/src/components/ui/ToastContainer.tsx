import { useToastStore } from "../../stores/toastStore";
import { XMarkIcon } from "@heroicons/react/24/outline";

const typeStyles: Record<string, string> = {
  success: "bg-success/90 text-white border border-success/30 backdrop-blur-sm",
  error: "bg-error/90 text-white border border-error/30 backdrop-blur-sm",
  warning: "bg-warning/90 text-black border border-warning/30 backdrop-blur-sm",
  info: "bg-primary-600/90 text-white border border-primary-500/30 backdrop-blur-sm",
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-2 px-4 py-3 rounded-lg shadow-lg text-sm animate-slide-up ${typeStyles[t.type]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => removeToast(t.id)}
            className="shrink-0 p-0.5 rounded hover:bg-white/20 transition-colors"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
