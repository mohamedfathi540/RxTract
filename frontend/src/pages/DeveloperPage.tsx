import { useState, useEffect } from "react";
import { KeyIcon, DocumentDuplicateIcon, TrashIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import { authApi } from "../api/auth";
import { useToastStore } from "../stores/toastStore";

export function DeveloperPage() {
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const addToast = useToastStore((s) => s.addToast);

  const fetchStatus = async () => {
    try {
      setIsLoading(true);
      const res = await authApi.getApiKeyStatus();
      setHasKey(res.has_key);
    } catch (err: any) {
      addToast(err.message || "Failed to check API key status", "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleGenerate = async () => {
    if (!window.confirm("Are you sure you want to generate a new API key? If you already have one, the old one will be replaced and invalidated immediately.")) {
      return;
    }
    try {
      setIsLoading(true);
      const res = await authApi.generateApiKey();
      setNewKey(res.api_key);
      setHasKey(true);
      addToast(res.message, "success");
    } catch (err: any) {
      addToast(err.message || "Failed to generate API key", "error");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevoke = async () => {
    if (!window.confirm("Are you sure you want to revoke your API key? This action cannot be undone and will break any apps currently using your key.")) {
      return;
    }
    try {
      setIsLoading(true);
      const res = await authApi.revokeApiKey();
      setHasKey(false);
      setNewKey(null);
      addToast(res.message, "success");
    } catch (err: any) {
      addToast(err.message || "Failed to revoke API key", "error");
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      addToast("Copied to clipboard!", "success");
    });
  };

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-3 border-b border-border pb-4">
        <div className="p-2.5 rounded-xl bg-primary-500/20 text-primary-400">
          <KeyIcon className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Developer API</h1>
          <p className="text-sm text-text-muted mt-0.5">Manage your API keys and integrate RxTract into your own applications.</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="bg-bg-secondary border border-border rounded-xl p-6 shadow-sm space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">API Key Management</h2>
            <p className="text-sm text-text-muted mt-1">
              Your API key grants access to the RxTract public extraction endpoint. Keep it secure and never commit it to source control.
            </p>
          </div>

          {isLoading ? (
            <div className="h-20 flex items-center justify-center text-text-muted">Loading status...</div>
          ) : newKey ? (
            <div className="bg-success/10 border border-success/30 rounded-lg p-4 space-y-3">
              <h3 className="text-sm font-bold text-success">New API Key Generated</h3>
              <p className="text-xs text-text-muted">
                Please copy this key and store it securely. For security reasons, it will never be displayed again.
              </p>
              <div className="flex gap-2 items-center w-full">
                <code className="flex-1 min-w-0 block p-2 bg-bg-tertiary rounded border border-border font-mono text-sm break-all text-white">
                  {newKey}
                </code>
                <button
                  onClick={() => copyToClipboard(newKey)}
                  className="p-2 bg-bg-tertiary hover:bg-bg-hover rounded border border-border text-text-primary transition-colors flex-shrink-0"
                  title="Copy to clipboard"
                >
                  <DocumentDuplicateIcon className="w-5 h-5" />
                </button>
              </div>
              <button
                onClick={() => setNewKey(null)}
                className="text-xs text-primary-400 hover:text-primary-300 font-medium"
              >
                I have saved my key securely
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                Status:{" "}
                {hasKey ? (
                  <span className="text-success flex items-center gap-1.5 px-2 py-1 bg-success/10 rounded-md">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse" /> Active
                  </span>
                ) : (
                  <span className="text-text-muted">No active key</span>
                )}
              </div>

              <div className="flex flex-wrap gap-3 pt-2">
                {hasKey ? (
                  <>
                    <button
                      onClick={handleGenerate}
                      className="px-4 py-2 bg-bg-tertiary hover:bg-bg-hover text-text-primary border border-border rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      <ArrowPathIcon className="w-4 h-4" />
                      Regenerate Key
                    </button>
                    <button
                      onClick={handleRevoke}
                      className="px-4 py-2 bg-error/10 hover:bg-error/20 text-error border border-error/20 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      <TrashIcon className="w-4 h-4" />
                      Revoke Key
                    </button>
                  </>
                ) : (
                  <button
                    onClick={handleGenerate}
                    className="px-4 py-2 bg-primary-600 hover:bg-primary-500 text-white rounded-lg text-sm font-medium shadow-sm shadow-primary-500/20 transition-all flex items-center gap-2"
                  >
                    <KeyIcon className="w-4 h-4" />
                    Generate API Key
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="bg-bg-secondary border border-border rounded-xl p-6 shadow-sm space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Quick Start</h2>
            <p className="text-sm text-text-muted mt-1">
              Use your API key to extract structured data from prescription images.
            </p>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">cURL Example</h3>
                <button 
                  onClick={() => copyToClipboard(`curl -X POST http://localhost:8001/api/v1/extract \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@/path/to/prescription.jpg"`)}
                  className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                >
                  <DocumentDuplicateIcon className="w-3 h-3" /> Copy
                </button>
              </div>
              <pre className="p-3 bg-bg-tertiary rounded-lg border border-border overflow-x-auto text-xs font-mono text-text-secondary leading-relaxed">
{`curl -X POST http://localhost:8001/api/v1/extract \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@/path/to/prescription.jpg"`}
              </pre>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">Python Example</h3>
                <button 
                  onClick={() => copyToClipboard(`import requests

url = "http://localhost:8001/api/v1/extract"
headers = {"X-API-Key": "YOUR_API_KEY"}
files = {"file": open("prescription.jpg", "rb")}

response = requests.post(url, headers=headers, files=files)
print(response.json())`)}
                  className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                >
                  <DocumentDuplicateIcon className="w-3 h-3" /> Copy
                </button>
              </div>
              <pre className="p-3 bg-bg-tertiary rounded-lg border border-border overflow-x-auto text-xs font-mono text-text-secondary leading-relaxed">
{`import requests

url = "http://localhost:8001/api/v1/extract"
headers = {"X-API-Key": "YOUR_API_KEY"}
files = {"file": open("prescription.jpg", "rb")}

response = requests.post(url, headers=headers, files=files)
print(response.json())`}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
