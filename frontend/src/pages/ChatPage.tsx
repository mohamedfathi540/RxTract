import { useState, useRef, useEffect, useCallback } from "react";
import { PaperAirplaneIcon, StopIcon } from "@heroicons/react/24/outline";
import ReactMarkdown from "react-markdown";
import { MessageCircle, ClipboardList, Link as LinkIcon, Lightbulb } from "lucide-react";
import { useSettingsStore } from "../stores/settingsStore";
import { useParams } from "react-router-dom";
import { chatAboutPrescriptionStream, fetchPrescription } from "../api/prescription";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { generateId, formatDate } from "../utils/helpers";
import type { ChatMessage } from "../api/types";

// ── Suggested question templates ────────────────────────────────────────────
const SUGGESTION_TEMPLATES = [
  "What can I use instead of {med}?",
  "What are the side effects of {med}?",
  "Can I take {med} with food?",
  "Is {med} safe during pregnancy?",
];

export function ChatPage() {
  const { prescriptionResult, chatHistory, addMessage, updateMessage, clearHistory } =
    useSettingsStore();
  const { id: routeId } = useParams<{ id: string }>();
  const [question, setQuestion] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [isLoadingPrescription, setIsLoadingPrescription] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const projectId = prescriptionResult?.projectId ?? null;

  // Load prescription if routeId changes and doesn't match current projectId
  useEffect(() => {
    if (routeId && routeId !== String(projectId)) {
      const loadData = async () => {
        setIsLoadingPrescription(true);
        try {
          const data = await fetchPrescription(routeId);
          useSettingsStore.setState({
            prescriptionResult: {
              ocrText: data.ocr_text,
              projectId: data.project_id,
              previewDataUrl: data.image_url ? `${useSettingsStore.getState().apiUrl.replace(/\/api\/v1\/?$/, '')}${data.image_url}` : null,
              medicines: data.medicines,
              signal: data.signal,
              doctorSpecialty: data.doctor_specialty
            },
            chatHistory: []
          });
        } catch (error) {
          console.error("Failed to load prescription", error);
        } finally {
          setIsLoadingPrescription(false);
        }
      };
      loadData();
    }
  }, [routeId, projectId]);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory]);

  // Cleanup: abort any in-flight stream on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.();
    };
  }, []);

  const handleSubmit = useCallback(
    (text: string) => {
      if (!text.trim() || isStreaming || !projectId) return;

      // 1. Add user message
      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };
      addMessage(userMsg);
      setQuestion("");

      // 2. Add empty assistant placeholder that will be filled by stream chunks
      const assistantId = generateId();
      const placeholderMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
      };
      addMessage(placeholderMsg);
      setStreamingId(assistantId);
      setIsStreaming(true);

      let accumulated = "";

      const { abort } = chatAboutPrescriptionStream(
        { text, limit: 5, project_id: projectId },
        // onChunk
        (chunk) => {
          accumulated += chunk;
          updateMessage(assistantId, accumulated);
        },
        // onDone
        () => {
          setIsStreaming(false);
          setStreamingId(null);
          abortRef.current = null;
        },
        // onError
        (err) => {
          if (err.startsWith("__RATE_LIMIT__")) return; // toast already shown
          updateMessage(assistantId, `Error: ${err}`);
          setIsStreaming(false);
          setStreamingId(null);
          abortRef.current = null;
        },
      );

      abortRef.current = abort;
    },
    [isStreaming, projectId, addMessage, updateMessage]
  );

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSubmit(question);
  };

  const handleAbort = () => {
    abortRef.current?.();
    abortRef.current = null;
    if (streamingId) {
      updateMessage(streamingId, "(Response cancelled)");
    }
    setIsStreaming(false);
    setStreamingId(null);
  };

  // Build suggestion pills from the first medicine in the prescription
  const firstMed = prescriptionResult?.medicines[0]?.name ?? "this medicine";
  const suggestions = SUGGESTION_TEMPLATES.map((t) => t.replace("{med}", firstMed));

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 5rem)" }}>
      {/* Header */}
      <div className="shrink-0 mb-4">
        <h2 className="text-2xl font-semibold text-text-primary tracking-tight flex items-center gap-2">
          <MessageCircle className="w-6 h-6 text-primary-400" /> Prescription Chat
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Ask questions about your prescription — find replacements, check
          interactions, and more
        </p>
      </div>

      {/* No Prescription Prompt */}
      {!projectId && !isLoadingPrescription ? (
        <Card className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3 max-w-md">
            <ClipboardList className="w-12 h-12 text-text-muted mx-auto" />
            <p className="text-lg text-text-primary font-medium">
              No Prescription Analyzed Yet
            </p>
            <p className="text-sm text-text-secondary">
              Go to the <strong>Prescription Analyzer</strong> page first to
              upload and analyze a prescription. Once analyzed, you can come back
              here to chat about the medicines.
            </p>
          </div>
        </Card>
      ) : isLoadingPrescription ? (
        <Card className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-text-secondary">Loading prescription data...</p>
          </div>
        </Card>
      ) : (
        <>
          {/* Prescription Context Banner */}
          {prescriptionResult && prescriptionResult.medicines.length > 0 && (
            <div className="mb-4 bg-primary-600/10 border border-primary-600/30 rounded-xl px-4 py-3">
              <p className="text-sm text-primary-400 font-medium flex items-center gap-1.5">
                <LinkIcon className="w-4 h-4" /> Chatting about{" "}
                {prescriptionResult.medicines.length} medicine
                {prescriptionResult.medicines.length > 1 ? "s" : ""}:{" "}
                <span className="text-primary-300">
                  {prescriptionResult.medicines.map((m) => m.name).join(", ")}
                </span>
              </p>
            </div>
          )}

          {/* Chat Container */}
          <div className="flex-1 min-h-0 flex flex-col bg-bg-secondary border border-border rounded-xl overflow-hidden">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {chatHistory.length === 0 ? (
                /* Empty state with suggested questions */
                <div className="flex flex-col items-center justify-center h-full gap-5 px-4">
                  <div className="text-center">
                    <Lightbulb className="w-8 h-8 text-primary-400 mx-auto mb-2" />
                    <p className="text-lg font-medium text-text-primary">
                      Ask about your medicines
                    </p>
                    <p className="text-sm text-text-secondary mt-1">
                      Try one of these to get started:
                    </p>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl w-full">
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        id={`suggestion-${s.slice(0, 20).replace(/\s+/g, "-").toLowerCase()}`}
                        onClick={() => handleSubmit(s)}
                        disabled={isStreaming}
                        className="px-3 py-2 text-sm text-left bg-bg-tertiary hover:bg-bg-hover
                                   border border-border rounded-lg text-text-secondary
                                   hover:text-text-primary hover:border-primary-600/50
                                   transition-all duration-150 disabled:opacity-50"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                chatHistory.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
                      }`}
                  >
                    <div
                      className={`max-w-[90%] sm:max-w-[85%] rounded-2xl px-3 sm:px-4 py-3 ${message.role === "user"
                          ? "bg-primary-600 text-white rounded-br-none"
                          : "bg-bg-tertiary text-text-primary border border-border rounded-bl-none"
                        }`}
                    >
                      {message.role === "user" ? (
                        <p className="whitespace-pre-wrap" dir="auto">{message.content}</p>
                      ) : (
                        <div className="prose-chat" dir="auto">
                          {message.content === "" && streamingId === message.id ? (
                            /* Typing indicator while streaming hasn't sent first chunk yet */
                            <div className="flex items-center gap-1.5 py-1">
                              <div className="w-2 h-2 bg-primary-400 rounded-full animate-bounce" />
                              <div className="w-2 h-2 bg-primary-400 rounded-full animate-bounce delay-100" />
                              <div className="w-2 h-2 bg-primary-400 rounded-full animate-bounce delay-200" />
                            </div>
                          ) : (
                            <ReactMarkdown
                              components={{
                                p: ({ node, ...props }) => <p dir="auto" {...props} />,
                                h1: ({ node, ...props }) => <h1 dir="auto" {...props} />,
                                h2: ({ node, ...props }) => <h2 dir="auto" {...props} />,
                                h3: ({ node, ...props }) => <h3 dir="auto" {...props} />,
                                h4: ({ node, ...props }) => <h4 dir="auto" {...props} />,
                                h5: ({ node, ...props }) => <h5 dir="auto" {...props} />,
                                h6: ({ node, ...props }) => <h6 dir="auto" {...props} />,
                                ul: ({ node, ...props }) => <ul dir="auto" {...props} />,
                                ol: ({ node, ...props }) => <ol dir="auto" {...props} />,
                                li: ({ node, ...props }) => <li dir="auto" {...props} />,
                                span: ({ node, ...props }) => <span dir="auto" {...props} />,
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          )}
                          {/* Streaming cursor */}
                          {streamingId === message.id && message.content && (
                            <span className="inline-block w-0.5 h-4 bg-primary-400 ml-0.5 animate-pulse align-middle" />
                          )}
                        </div>
                      )}
                      <span className="text-xs opacity-70 mt-2 block">
                        {formatDate(message.timestamp)}
                      </span>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="border-t border-border p-4 bg-bg-secondary">
              {chatHistory.length > 0 && (
                <div className="mb-3 flex justify-end">
                  <Button variant="ghost" size="sm" onPress={clearHistory} isDisabled={isStreaming}>
                    Clear History
                  </Button>
                </div>
              )}

              <form onSubmit={handleFormSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about your medicines..."
                  disabled={isStreaming}
                  className="flex-1 min-w-0 px-3 sm:px-4 py-3 bg-bg-tertiary border border-border rounded-md
                             text-text-primary placeholder-text-muted focus:outline-none
                             focus:border-primary-600 disabled:opacity-50 transition-all text-base"
                />
                {isStreaming ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onPress={handleAbort}
                    className="shrink-0"
                  >
                    <StopIcon className="w-5 h-5" />
                    Stop
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    isDisabled={!question.trim() || !projectId}
                    className="shrink-0"
                  >
                    <PaperAirplaneIcon className="w-5 h-5" />
                    Send
                  </Button>
                )}
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
