"use client";

import { useMemo, useState } from "react";

type Citation = { page: number | null; section: string | null; snippet: string | null };

type Segment = { type: "text"; value: string } | { type: "citation"; pages: number[] };

// Matches a parenthetical citation cluster like "(page 36, Revenues; page 82, ...)"
// or "(pages 26, 60)" - the same phrasing convention the backend's own prompts
// instruct the model to use (see AGENT_SYSTEM_PROMPT's citation rules).
const PAREN_CITATION_RE = /\(([^)]*\bpages?\s+\d+[^)]*)\)/gi;
const PAGE_NUMBER_RE = /pages?\s+(\d[\d,\-\s]*\d|\d+)/gi;

function parseAnswerSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  PAREN_CITATION_RE.lastIndex = 0;

  while ((match = PAREN_CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    const pages: number[] = [];
    let pageMatch: RegExpExecArray | null;
    PAGE_NUMBER_RE.lastIndex = 0;
    while ((pageMatch = PAGE_NUMBER_RE.exec(match[1])) !== null) {
      (pageMatch[1].match(/\d+/g) ?? []).forEach((n) => pages.push(parseInt(n, 10)));
    }
    segments.push({ type: "citation", pages: Array.from(new Set(pages)) });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  return segments;
}

export default function AnswerWithCitations({
  content,
  citations,
}: {
  content: string;
  citations: Citation[];
}) {
  const [expandedPage, setExpandedPage] = useState<number | null>(null);
  const segments = useMemo(() => parseAnswerSegments(content), [content]);

  const usedPages = useMemo(() => {
    const set = new Set<number>();
    segments.forEach((seg) => {
      if (seg.type === "citation") seg.pages.forEach((p) => set.add(p));
    });
    return set;
  }, [segments]);

  const unmentioned = citations.filter((c) => c.page !== null && !usedPages.has(c.page));
  const expandedCitation = citations.find((c) => c.page === expandedPage);

  function toggle(page: number) {
    setExpandedPage((current) => (current === page ? null : page));
  }

  // Nothing was parsed as a citation cluster (e.g. a refusal/no-citation
  // answer) - render as plain text, matching the old behavior exactly.
  const hasChips = segments.some((seg) => seg.type === "citation");
  if (!hasChips) {
    return (
      <div>
        <p className="whitespace-pre-wrap text-sm leading-6">{content}</p>
        {citations.length > 0 ? (
          <details className="mt-3 text-xs text-slate-600">
            <summary className="cursor-pointer font-medium">Sources ({citations.length})</summary>
            <div className="mt-2 space-y-2">
              {citations.map((citation, idx) => (
                <p key={idx}>
                  Page {citation.page ?? "n/a"}, {citation.section ?? "section n/a"}:{" "}
                  {citation.snippet ?? "No snippet"}
                </p>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <p className="whitespace-pre-wrap text-sm leading-6">
        {segments.map((seg, i) =>
          seg.type === "text" ? (
            <span key={i}>{seg.value}</span>
          ) : (
            <span key={i} className="whitespace-nowrap">
              {seg.pages.map((page) => (
                <button
                  key={page}
                  type="button"
                  onClick={() => toggle(page)}
                  aria-expanded={expandedPage === page}
                  className={`mx-0.5 inline-flex h-8 min-w-[32px] items-center justify-center rounded-full border px-2 align-middle text-xs font-medium tabular-nums shadow-sm ${
                    expandedPage === page
                      ? "border-sky-600 bg-sky-50 text-sky-900"
                      : "border-slate-300 bg-white text-slate-700"
                  }`}
                >
                  p.&nbsp;{page}
                </button>
              ))}
            </span>
          )
        )}
      </p>

      {expandedCitation ? (
        <div className="mt-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-xs text-slate-700">
          <p className="font-medium text-slate-900">
            Page {expandedCitation.page}, {expandedCitation.section ?? "section n/a"}
          </p>
          <p className="mt-1">{expandedCitation.snippet ?? "No snippet"}</p>
        </div>
      ) : null}

      {unmentioned.length > 0 ? (
        <details className="mt-3 text-xs text-slate-600">
          <summary className="cursor-pointer font-medium">Sources ({unmentioned.length})</summary>
          <div className="mt-2 space-y-2">
            {unmentioned.map((citation, idx) => (
              <p key={idx}>
                Page {citation.page ?? "n/a"}, {citation.section ?? "section n/a"}:{" "}
                {citation.snippet ?? "No snippet"}
              </p>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}
