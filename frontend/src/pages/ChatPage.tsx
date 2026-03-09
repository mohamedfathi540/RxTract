import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { PaperAirplaneIcon } from "@heroicons/react/24/outline";
import ReactMarkdown from "react-markdown";
import { MessageCircle, ClipboardList, Link as LinkIcon } from "lucide-react";
import { useSettingsStore } from "../stores/settingsStore";
import { chatAboutPrescription } from "../api/prescription";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { generateId, formatDate } from "../utils/helpers";
import type { ChatMessage } from "../api/types";

export function ChatPage() {
  const { prescriptionResult, chatHistory, addMessage, clearHistory } =
    useSettingsStore();
  const [question, setQuestion] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const projectId = prescriptionResult?.projectId ?? null;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory]);

  const answerMutation = useMutation({
    mutationFn: (text: string) => {
      if (!projectId) throw new Error("No prescription analyzed yet");
      return chatAboutPrescription({
        text,
        limit: 5,
        project_id: projectId,
      });
    },
    onSuccess: (data) => {
      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: data.Answer,
        timestamp: new Date().toISOString(),
        metadata: {
          fullPrompt: data.FullPrompt,
          chatHistory: data.ChatHistory,
        },
      };
      addMessage(assistantMessage);
    },
    onError: (error) => {
      // Rate-limit errors are already shown as a warning toast — skip chat error
      if (error && 'isRateLimit' in error && (error as any).isRateLimit) return;
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: `Error: ${error instanceof Error ? error.message : "Failed to get answer"}`,
        timestamp: new Date().toISOString(),
      };
      addMessage(errorMessage);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || answerMutation.isPending || !projectId) return;

    const userMessage: ChatMessage = {
      id: generateId(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };
    addMessage(userMessage);
    answerMutation.mutate(question);
    setQuestion("");
  };

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
      {!projectId ? (
        <Card className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3 max-w-md">
            <ClipboardList className="w-12 h-12 text-text-muted" />
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
      ) : (
        <>
          {/* Prescription Context Banner */}
          {prescriptionResult && prescriptionResult.medicines.length > 0 && (
            <div className="mb-4 bg-primary-600/10 border border-primary-600/30 rounded-xl px-4 py-3">
              <p className="text-sm text-primary-400 font-medium flex items-center gap-1.5">
                <LinkIcon className="w-4 h-4" /> Chatting about {prescriptionResult.medicines.length} medicine
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
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <p className="text-lg mb-2 text-text-primary">
                      Ask about your medicines
                    </p>
                    <p className="text-sm text-text-secondary">
                      Try: "What can I use instead of {prescriptionResult?.medicines[0]?.name ?? 'this medicine'}?"
                    </p>
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
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      ) : (
                        <div className="prose-chat">
                          <ReactMarkdown>{message.content}</ReactMarkdown>
                        </div>
                      )}
                      <span className="text-xs opacity-70 mt-2 block">
                        {formatDate(message.timestamp)}
                      </span>
                    </div>
                  </div>
                ))
              )}
              {answerMutation.isPending && (
                <div className="flex justify-start">
                  <div className="bg-bg-tertiary border border-border rounded-2xl rounded-bl-none px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-primary-600 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-primary-600 rounded-full animate-bounce delay-100" />
                      <div className="w-2 h-2 bg-primary-600 rounded-full animate-bounce delay-200" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="border-t border-border p-4 bg-bg-secondary">
              {chatHistory.length > 0 && (
                <div className="mb-3 flex justify-end">
                  <Button variant="ghost" size="sm" onPress={clearHistory}>
                    Clear History
                  </Button>
                </div>
              )}

              {/* Input Form */}
              <form onSubmit={handleSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about your medicines..."
                  disabled={answerMutation.isPending}
                  className="flex-1 min-w-0 px-3 sm:px-4 py-3 bg-bg-tertiary border border-border rounded-md text-text-primary placeholder-text-muted focus:outline-none focus:border-primary-600 disabled:opacity-50 transition-all text-base"
                />
                <Button
                  type="submit"
                  isLoading={answerMutation.isPending}
                  isDisabled={!question.trim()}
                >
                  <PaperAirplaneIcon className="w-5 h-5" />
                  Send
                </Button>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
