import { useSettingsStore } from "../stores/settingsStore";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Logo } from "../components/ui/Logo";

export function SettingsPage() {
  const {
    apiUrl,
    setApiUrl,
    projectId,
    setProjectId,
    theme,
    toggleTheme,
    clearHistory,
  } = useSettingsStore();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-semibold text-text-primary tracking-tight">
          Settings
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Configure your RxTract application
        </p>
      </div>

      {/* API Configuration */}
      <Card title="API Configuration">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              API Base URL
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="/api/v1"
              className="w-full px-4 py-2 bg-bg-tertiary border border-border rounded-md text-text-primary focus:outline-none focus:border-primary-600 transition-all"
            />
            <p className="text-xs text-text-muted mt-1">
              The base URL for the RxTract API
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Project ID
            </label>
            <input
              type="number"
              min={1}
              value={projectId}
              onChange={(e) => setProjectId(parseInt(e.target.value) || 1)}
              className="w-full px-4 py-2 bg-bg-tertiary border border-border rounded-md text-text-primary focus:outline-none focus:border-primary-600 transition-all"
            />
            <p className="text-xs text-text-muted mt-1">
              The project to work with. Use <strong>10</strong> for the learning
              books corpus (AI/Data Science references; book chunk size and
              hybrid search).
            </p>
          </div>
        </div>
      </Card>

      {/* Appearance */}
      <Card title="Appearance">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-text-primary font-medium">Dark Mode</h4>
            <p className="text-sm text-text-muted">Toggle dark/light theme</p>
          </div>
          <button
            onClick={toggleTheme}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${theme === "dark" ? "bg-primary-600" : "bg-bg-hover"
              }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${theme === "dark" ? "translate-x-6" : "translate-x-1"
                }`}
            />
          </button>
        </div>
      </Card>

      {/* Data Management */}
      <Card title="Data Management">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-text-primary font-medium">
              Clear Chat History
            </h4>
            <p className="text-sm text-text-muted">
              Remove all chat messages from local storage
            </p>
          </div>
          <Button variant="danger" onPress={clearHistory}>
            Clear History
          </Button>
        </div>
      </Card>

      {/* Quick Links */}
      <Card title="Quick Links">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <a
            href="http://localhost:3000"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-bg-tertiary rounded-md border border-border hover:border-primary-600 transition-colors text-center"
          >
            <div className="text-text-primary font-medium">Grafana</div>
            <div className="text-xs text-text-muted mt-1">Metrics</div>
          </a>
          <a
            href="http://localhost:9090"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-bg-tertiary rounded-md border border-border hover:border-primary-600 transition-colors text-center"
          >
            <div className="text-text-primary font-medium">Prometheus</div>
            <div className="text-xs text-text-muted mt-1">Monitoring</div>
          </a>
          <a
            href="http://localhost:6333/dashboard"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-bg-tertiary rounded-md border border-border hover:border-primary-600 transition-colors text-center"
          >
            <div className="text-text-primary font-medium">Qdrant</div>
            <div className="text-xs text-text-muted mt-1">Vector DB</div>
          </a>
          <a
            href="/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-bg-tertiary rounded-md border border-border hover:border-primary-600 transition-colors text-center"
          >
            <div className="text-text-primary font-medium">API Docs</div>
            <div className="text-xs text-text-muted mt-1">Swagger</div>
          </a>
        </div>
      </Card>

      {/* About */}
      <Card title="About">
        <div className="text-center py-4">
          <Logo size={64} className="mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-text-primary mb-2">RxTract</h1>
          <p className="text-text-secondary">RAG System</p>
          <p className="text-sm text-text-muted mt-4">
            A modern frontend for the RxTract RAG API built with React and React
            Aria
          </p>
        </div>
      </Card>
    </div>
  );
}
