import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { MagnifyingGlassIcon } from "@heroicons/react/24/outline";
import { useSettingsStore } from "../stores/settingsStore";
import { searchIndex } from "../api/nlp";
import { searchMedicine } from "../api/data";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ChevronDown, ChevronRight, BookOpen, Pill, AlertTriangle } from "lucide-react";
import { truncateText } from "../utils/helpers";
import type { SearchResult, SearchMedicineResult } from "../api/types";

export function SearchPage() {
  const { projectId } = useSettingsStore();
  const [activeTab, setActiveTab] = useState<"medicine" | "documents">("medicine");
  
  // Document Search State
  const [docQuery, setDocQuery] = useState("");
  const [docLimit, setDocLimit] = useState(5);
  const [expandedResults, setExpandedResults] = useState<Set<number>>(new Set());

  // Medicine Search State
  const [medQuery, setMedQuery] = useState("");
  const [medLimit, setMedLimit] = useState(15);
  const [searchedMedQuery, setSearchedMedQuery] = useState("");

  const docSearchMutation = useMutation({
    mutationFn: () => searchIndex(projectId, { text: docQuery, limit: docLimit }),
  });

  const { data: medData, isFetching: isFetchingMeds, isError: isMedError, error: medError } = useQuery({
    queryKey: ["searchMedicine", searchedMedQuery, medLimit],
    queryFn: () => searchMedicine(searchedMedQuery, medLimit),
    enabled: !!searchedMedQuery,
  });

  const handleDocSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!docQuery.trim()) return;
    docSearchMutation.mutate();
    setExpandedResults(new Set());
  };

  const handleMedSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!medQuery.trim()) return;
    setSearchedMedQuery(medQuery);
  };

  const toggleResult = (index: number) => {
    setExpandedResults((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const docResults: SearchResult[] = docSearchMutation.data?.Results || [];
  const medResults: SearchMedicineResult[] = medData?.results || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-semibold text-text-primary tracking-tight">
          System Search
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Look up specific medicines or semantic documents using the search tools below.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab("medicine")}
          className={`px-6 py-3 font-medium text-sm flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === "medicine"
              ? "border-primary-500 text-primary-400"
              : "border-transparent text-text-muted hover:text-text-primary hover:border-bg-hover"
          }`}
        >
          <Pill className="w-4 h-4" />
          Egyptian Medicines
        </button>
        <button
          onClick={() => setActiveTab("documents")}
          className={`px-6 py-3 font-medium text-sm flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === "documents"
              ? "border-primary-500 text-primary-400"
              : "border-transparent text-text-muted hover:text-text-primary hover:border-bg-hover"
          }`}
        >
          <BookOpen className="w-4 h-4" />
          Document Index
        </button>
      </div>

      {/* Medicine Tab */}
      {activeTab === "medicine" && (
        <div className="space-y-6 animate-fade-in">
          <Card>
            <form onSubmit={handleMedSearch} className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={medQuery}
                  onChange={(e) => setMedQuery(e.target.value)}
                  placeholder="Enter a medication or trade name..."
                  className="flex-1 min-w-0 px-3 sm:px-4 py-3 bg-bg-primary border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary-500 text-base"
                />
                <Button
                  type="submit"
                  isLoading={isFetchingMeds}
                  isDisabled={!medQuery.trim()}
                >
                  <MagnifyingGlassIcon className="w-5 h-5" />
                  Search
                </Button>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Results Limit: {medLimit}
                </label>
                <input
                  type="range"
                  min={5}
                  max={50}
                  step={5}
                  value={medLimit}
                  onChange={(e) => setMedLimit(parseInt(e.target.value))}
                  className="w-full"
                />
              </div>
            </form>
          </Card>

          {searchedMedQuery && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-text-primary">
                  Search Results
                </h3>
                <span className="text-sm text-text-secondary">
                  Found {medResults.length} matches
                </span>
              </div>

              {medResults.length > 0 ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {medResults.map((med, index) => (
                    <Card key={index} className="animate-slide-up flex flex-col justify-between overflow-hidden p-0">
                      {med.image_url && (
                        <div className="h-40 w-full mb-0 rounded-t-lg overflow-hidden bg-bg-secondary flex items-center justify-center border-b border-border">
                          <img
                            src={med.image_url}
                            alt={med.trade_name}
                            className="object-cover w-full h-full hover:scale-105 transition-transform duration-300"
                            loading="lazy"
                            onError={(e) => {
                              (e.target as HTMLImageElement).src = "https://placehold.co/400x300/1E293B/A4A4A4?text=Image+Unavailable";
                            }}
                          />
                        </div>
                      )}
                      <div className="flex-1 p-5">
                        <h4 className="text-lg font-bold text-primary-400 mb-1">
                          {med.trade_name}
                        </h4>
                        <p className="text-xs uppercase tracking-wider text-text-muted font-medium mt-3">
                          Active Ingredient
                        </p>
                        <p className="text-sm text-text-secondary font-medium mt-0.5 break-words line-clamp-2">
                          {med.active_ingredient && med.active_ingredient !== "Unknown" 
                             ? med.active_ingredient 
                             : "Not clearly specified"}
                        </p>
                      </div>
                      
                      {med.product_url && (
                        <div className="p-5 pt-0 mt-auto">
                          <div className="pt-4 border-t border-border">
                            <a
                              href={med.product_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium text-primary-400 hover:text-primary-300 flex items-center gap-1 group"
                            >
                              Check Availability
                              <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                            </a>
                          </div>
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              ) : !isFetchingMeds && !isMedError ? (
                <Card className="text-center py-10 border-dashed">
                  <p className="text-text-muted">No medicines found matching "{searchedMedQuery}".</p>
                  <p className="text-xs text-text-secondary mt-2">Try a partial name or check for typos.</p>
                </Card>
              ) : null}

              {isMedError && (
                <Card className="border-red-500/30 bg-red-500/10">
                  <p className="text-red-400 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    Failed to search medicine database. {(medError as Error)?.message}
                  </p>
                </Card>
              )}
            </div>
          )}
        </div>
      )}

      {/* Documents Tab */}
      {activeTab === "documents" && (
        <div className="space-y-6 animate-fade-in">
          <Card>
            <form onSubmit={handleDocSearch} className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={docQuery}
                  onChange={(e) => setDocQuery(e.target.value)}
                  placeholder="Enter your document query..."
                  className="flex-1 min-w-0 px-3 sm:px-4 py-3 bg-bg-primary border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary-500 text-base"
                />
                <Button
                  type="submit"
                  isLoading={docSearchMutation.isPending}
                  isDisabled={!docQuery.trim()}
                >
                  <MagnifyingGlassIcon className="w-5 h-5" />
                  Search
                </Button>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Results Limit: {docLimit}
                </label>
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={docLimit}
                  onChange={(e) => setDocLimit(parseInt(e.target.value))}
                  className="w-full"
                />
              </div>
            </form>
          </Card>

          {docSearchMutation.isSuccess && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-text-primary">
                  Document Results
                </h3>
                <span className="text-sm text-text-secondary">
                  Found {docResults.length} results
                </span>
              </div>

              {docResults.map((result, index) => {
                const isExpanded = expandedResults.has(index);
                return (
                  <Card key={index} className="animate-slide-up">
                    <div
                      className="flex items-start justify-between cursor-pointer"
                      onClick={() => toggleResult(index)}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm font-medium text-primary-400">
                            Result #{index + 1}
                          </span>
                          <span className="text-sm text-yellow-400 font-semibold">
                            Score: {result.score.toFixed(4)}
                          </span>
                        </div>
                        <p className="text-text-primary leading-relaxed text-sm">
                          {isExpanded ? result.text : truncateText(result.text, 200)}
                        </p>
                      </div>
                      <button className="ml-4 text-text-muted hover:text-text-primary p-1">
                        {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>
                    </div>

                    {isExpanded && result.metadata && (
                      <div className="mt-4 pt-4 border-t border-border">
                        <h4 className="text-sm font-medium text-text-secondary mb-2">
                          Metadata
                        </h4>
                        <pre className="bg-bg-primary p-3 rounded-lg text-xs text-text-secondary overflow-x-auto border border-border">
                          {JSON.stringify(result.metadata, null, 2)}
                        </pre>
                      </div>
                    )}
                  </Card>
                );
              })}
              
              {docResults.length === 0 && (
                <Card className="text-center py-10 border-dashed">
                  <p className="text-text-muted">No documents found matching "{docQuery}".</p>
                </Card>
              )}
            </div>
          )}

          {docSearchMutation.isError && !(docSearchMutation.error && 'isRateLimit' in docSearchMutation.error && (docSearchMutation.error as any).isRateLimit) && (
            <Card className="border-red-500/30 bg-red-500/10">
              <p className="text-red-400 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5" />
                Error:{" "}
                {docSearchMutation.error instanceof Error ? docSearchMutation.error.message : "Search failed"}
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
