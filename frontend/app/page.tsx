"use client";

import { FormEvent, useState } from "react";
import AnswerWithCitations from "./components/AnswerWithCitations";
import MemoDocument, { MemoDocumentData } from "./components/MemoDocument";

type Citation = {
  page: number | null;
  section: string | null;
  snippet: string | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  memo?: MemoDocumentData;
};

const filings = [
  { id: "boeing-2024-10k", label: "Boeing 2024 10-K" },
  { id: "lockheed-2024-10k", label: "Lockheed Martin 2024 10-K" },
  { id: "rtx-2024-10k", label: "RTX 2024 10-K" },
];

const SUGGESTED_QUESTIONS: Record<string, string[]> = {
  "boeing-2024-10k": [
    "What was Boeing's total consolidated revenue in FY2024?",
    "What liquidity risks did Boeing disclose?",
    "How did the 737 MAX issues affect 2024 production?",
  ],
  "lockheed-2024-10k": [
    "What were Lockheed Martin's net earnings in FY2024?",
    "What was Lockheed's total debt at year-end 2024?",
    "What risks does Lockheed disclose about U.S. government contract reliance?",
  ],
  "rtx-2024-10k": [
    "What was RTX's total net sales in FY2024?",
    "How much cash did RTX report at year-end 2024?",
    "What credit-relevant industry risks does RTX disclose?",
  ],
};

const INTRO_MESSAGE: Message = {
  role: "assistant",
  content: 'Select a filing and ask a credit question — e.g., "What was total revenue in FY2024?"',
};

function readOrCreateThreadId(): string {
  if (typeof window === "undefined") {
    return "server";
  }
  const existing = window.localStorage.getItem("creditlens_thread_id");
  if (existing) {
    return existing;
  }
  const created = crypto.randomUUID();
  window.localStorage.setItem("creditlens_thread_id", created);
  return created;
}

export default function Home() {
  const [selectedFiling, setSelectedFiling] = useState(filings[0].id);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([INTRO_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string>(() => readOrCreateThreadId());

  const hasUserMessages = messages.some((m) => m.role === "user");

  function handleNewConversation() {
    if (isLoading) {
      return;
    }
    const created = crypto.randomUUID();
    window.localStorage.setItem("creditlens_thread_id", created);
    // Rotating thread_id, not just clearing the UI, is the actual clear -
    // the backend's MemorySaver checkpointer is keyed by thread_id, so
    // reusing the old id would leave the agent still remembering the
    // "cleared" conversation on the very next follow-up question.
    setThreadId(created);
    setMessages([INTRO_MESSAGE]);
    setError(null);
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) {
      return;
    }

    setError(null);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          filing_id: selectedFiling,
          thread_id: threadId,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer,
          citations: data.citations ?? [],
        },
      ]);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Something went wrong";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || isLoading) {
      return;
    }
    setInput("");
    await sendMessage(message);
  }

  async function handleDraftMemo() {
    if (isLoading) {
      return;
    }

    setError(null);
    setMessages((current) => [
      ...current,
      {
        role: "user",
        content: `Draft memo section for ${filings.find((f) => f.id === selectedFiling)?.label ?? selectedFiling}`,
      },
    ]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/memo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filing_id: selectedFiling }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.narrative,
          citations: data.citations ?? [],
          memo: {
            company: data.company,
            fiscalYear: data.fiscal_year,
            figures: data.figures,
            narrative: data.narrative,
            citations: data.citations ?? [],
            filingId: selectedFiling,
          },
        },
      ]);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Something went wrong";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-5 sm:px-6">
        <header className="mb-5 flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-end sm:justify-between print:hidden">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">CreditLens</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              Cited SEC filing Q&A for commercial credit analysis.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
              Filing
              <select
                className="h-10 rounded-md border border-slate-300 bg-white px-3 text-slate-950 shadow-sm"
                value={selectedFiling}
                onChange={(event) => setSelectedFiling(event.target.value)}
              >
                {filings.map((filing) => (
                  <option key={filing.id} value={filing.id}>
                    {filing.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                className="h-10 rounded-md border border-slate-300 bg-white px-4 text-sm font-medium text-slate-950 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoading}
                onClick={handleDraftMemo}
              >
                Draft memo section
              </button>
              <button
                type="button"
                className="h-10 rounded-md border border-slate-300 bg-white px-4 text-sm font-medium text-slate-950 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoading}
                onClick={handleNewConversation}
              >
                New conversation
              </button>
            </div>
          </div>
        </header>

        <section className="flex flex-1 flex-col rounded-lg border border-slate-200 bg-white shadow-sm print:border-none print:bg-transparent print:shadow-none">
          <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
            {messages.map((message, index) =>
              message.memo ? (
                <div key={`${message.role}-${index}`}>
                  <MemoDocument data={message.memo} />
                </div>
              ) : (
                <article
                  key={`${message.role}-${index}`}
                  className={
                    message.role === "user"
                      ? "ml-auto max-w-2xl rounded-lg bg-slate-900 px-4 py-3 text-white print:hidden"
                      : "max-w-2xl rounded-lg bg-slate-100 px-4 py-3 text-slate-950 print:hidden"
                  }
                >
                  {message.role === "assistant" && message.citations ? (
                    <AnswerWithCitations content={message.content} citations={message.citations} />
                  ) : (
                    <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                  )}
                </article>
              )
            )}

            {!hasUserMessages ? (
              <div className="flex flex-wrap gap-2 print:hidden">
                {(SUGGESTED_QUESTIONS[selectedFiling] ?? []).map((question) => (
                  <button
                    key={question}
                    type="button"
                    disabled={isLoading}
                    onClick={() => void sendMessage(question)}
                    className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {question}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <form
            className="border-t border-slate-200 p-3 sm:flex sm:items-center sm:gap-3 print:hidden"
            onSubmit={handleSubmit}
          >
            <input
              className="h-11 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-700"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about liquidity, debt, risk factors, or cash flow..."
            />
            <button
              className="mt-3 h-11 w-full rounded-md bg-slate-900 px-5 font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400 sm:mt-0 sm:w-auto"
              disabled={isLoading}
              type="submit"
            >
              {isLoading ? "Sending" : "Send"}
            </button>
          </form>
          {error ? <p className="px-4 pb-4 text-sm text-red-700 print:hidden">{error}</p> : null}
        </section>
      </div>
    </main>
  );
}
