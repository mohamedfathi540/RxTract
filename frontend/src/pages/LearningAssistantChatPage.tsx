import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { PaperAirplaneIcon } from "@heroicons/react/24/outline";
import { useSettingsStore } from "../stores/settingsStore";
import { getAnswer } from "../api/nlp";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { generateId, formatDate } from "../utils/helpers";
import type { ChatMessage } from "../api/types";



export function LearningAssistantChatPage() {
  const { projectId } = useSettingsStore();
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [contextLimit, setContextLimit] = useState(5);

  const addMessage = (message: ChatMessage) => {
    setChatHistory((prev) => [...prev, message].slice(-50));
  };

  const clearHistory = () => setChatHistory([]);

  const answerMutation = useMutation({
    mutationFn: (text: string) =>
      getAnswer(projectId, { text, limit: contextLimit }),
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
    if (!question.trim() || answerMutation.isPending) return;

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
    <div className="flex flex-col h-[calc(100dvh-6rem)]">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-text-primary">
          Learning Assistant
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Ask questions about AI, Data Science, Maths, Statistics, ML, DL,
          GenAI, and System Design from the reference corpus.
        </p>
      </div>

      <Card className="flex-1 flex flex-col overflow-hidden" contentClassName="flex-1 flex flex-col min-h-0 p-0">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {chatHistory.length === 0 ?
            <div className="flex items-center justify-center h-full text-text-muted">
              <div className="text-center">
                <p className="text-lg mb-2">Learning Assistant</p>
                <p className="text-sm">
                  Ask anything about the learning books and references. Answers
                  are grounded in the indexed corpus.
                </p>
              </div>
            </div>
            : chatHistory.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
                  }`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${message.role === "user" ?
                    "bg-primary-500 text-white rounded-br-none"
                    : "bg-bg-tertiary text-text-primary border border-border rounded-bl-none"
                    }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  <span className="text-xs opacity-70 mt-2 block">
                    {formatDate(message.timestamp)}
                  </span>
                </div>
              </div>
            ))
          }
          {answerMutation.isPending && (
            <div className="flex justify-start">
              <div className="bg-bg-tertiary border border-border rounded-2xl rounded-bl-none px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce delay-100" />
                  <div className="w-2 h-2 bg-primary-500 rounded-full animate-bounce delay-200" />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-border p-4 bg-bg-secondary">
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-text-secondary">
                Context chunks: {contextLimit}
              </label>
              <div className="flex items-center gap-2">
                <label className="text-sm text-text-secondary">Project ID: <span className="font-medium text-text-primary">{projectId}</span></label>
              </div>
            </div>
            {chatHistory.length > 0 && (
              <Button variant="ghost" size="sm" onPress={clearHistory}>
                Clear history
              </Button>
            )}
          </div>
          <input
            type="range"
            min={1}
            max={10}
            value={contextLimit}
            onChange={(e) => setContextLimit(parseInt(e.target.value))}
            className="w-full"
          />
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about AI, Data Science, maths, ML..."
            disabled={answerMutation.isPending}
            className="flex-1 px-4 py-3 bg-bg-primary border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary-500 disabled:opacity-50"
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
      </Card>
    </div>
  );
}
