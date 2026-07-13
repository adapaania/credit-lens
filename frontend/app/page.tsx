"use client";

import { FormEvent, useMemo, useState } from "react";

type Citation = {
  page: number | null;
  section: string | null;
  snippet: string | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isMemo?: boolean;
};

const filings = [
  { id: "boeing-2024-10k", label: "Boeing 2024 10-K" },
  { id: "lockheed-2024-10k", label: "Lockheed Martin 2024 10-K" },
  { id: "rtx-2024-10k", label: "RTX 2024 10-K" },
];

export default function Home() {
  const [selectedFiling, setSelectedFiling] = useState(filings[0].id);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Select a filing and ask a credit question — e.g., \"What was total revenue in FY2024?\"",
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const threadId = useMemo(() => {
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
  }, []);

  async function handleDraftMemo() {
    if (isLoading) {
      return;
    }

    setError(null);
    setMessages((current) => [
      ...current,
      { role: "user", content: `Draft memo section for ${filings.find((f) => f.id === selectedFiling)?.label ?? selectedFiling}` },
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
          isMemo: true,
        },
      ]);
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "Something went wrong";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  function handleDownloadMemo(narrative: string) {
    const blob = new Blob([narrative], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selectedFiling}-memo.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || isLoading) {
      return;
    }

    setInput("");
    setError(null);
    setMessages((current) => [...current, { role: "user", content: message }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
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
      const message =
        requestError instanceof Error ? requestError.message : "Something went wrong";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-5 sm:px-6">
        <header className="mb-5 flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
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
            <button
              type="button"
              className="h-10 rounded-md border border-slate-300 bg-white px-4 text-sm font-medium text-slate-950 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isLoading}
              onClick={handleDraftMemo}
            >
              Draft memo section
            </button>
          </div>
        </header>

        <section className="flex flex-1 flex-col rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
            {messages.map((message, index) => (
              <article
                key={`${message.role}-${index}`}
                className={
                  message.role === "user"
                    ? "ml-auto max-w-2xl rounded-lg bg-slate-900 px-4 py-3 text-white"
                    : "max-w-2xl rounded-lg bg-slate-100 px-4 py-3 text-slate-950"
                }
              >
                <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                {message.citations && message.citations.length > 0 ? (
                  <div className="mt-3 space-y-2 border-t border-slate-300 pt-3 text-xs text-slate-600">
                    {message.citations.map((citation, citationIndex) => (
                      <p key={citationIndex}>
                        Page {citation.page ?? "n/a"}, {citation.section ?? "section n/a"}:{" "}
                        {citation.snippet ?? "No snippet"}
                      </p>
                    ))}
                  </div>
                ) : null}
                {message.isMemo ? (
                  <button
                    type="button"
                    className="mt-3 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-950 shadow-sm"
                    onClick={() => handleDownloadMemo(message.content)}
                  >
                    Download memo (.md)
                  </button>
                ) : null}
              </article>
            ))}
          </div>

          <form
            className="border-t border-slate-200 p-3 sm:flex sm:items-center sm:gap-3"
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
          {error ? <p className="px-4 pb-4 text-sm text-red-700">{error}</p> : null}
        </section>
      </div>
    </main>
  );
}
