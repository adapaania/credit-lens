"use client";

import InlineMarkdown from "./InlineMarkdown";
import {
  findSection,
  parseMemoSections,
  parseMemoSubtitle,
  splitFinancialAnalysis,
  toAccountingStyle,
} from "../lib/memoParse";

type CitedFigure = { value: number | null; page: number | null; section: string | null };

type MemoFigures = {
  revenue: CitedFigure;
  net_income: CitedFigure;
  total_debt: CitedFigure;
  cash: CitedFigure;
  current_assets: CitedFigure;
  current_liabilities: CitedFigure;
};

type Citation = { page: number | null; section: string | null; snippet: string | null };

export type MemoDocumentData = {
  company: string | null;
  fiscalYear: number | null;
  figures: MemoFigures;
  narrative: string;
  citations: Citation[];
  filingId: string;
};

const FIGURE_LABELS: Record<keyof MemoFigures, string> = {
  revenue: "Revenue",
  net_income: "Net income",
  total_debt: "Total debt",
  cash: "Cash and cash equivalents",
  current_assets: "Current assets",
  current_liabilities: "Current liabilities",
};

function formatFigureValue(figure: CitedFigure): string {
  if (figure.value === null) {
    return "Not disclosed in reviewed filings";
  }
  const sign = figure.value < 0 ? "-" : "";
  const formatted = `${sign}$${Math.abs(figure.value).toLocaleString("en-US", {
    maximumFractionDigits: 0,
  })} million`;
  return toAccountingStyle(formatted);
}

function handlePrint() {
  window.print();
}

function handleDownloadMarkdown(narrative: string, filingId: string) {
  const blob = new Blob([narrative], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filingId}-memo.md`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function MemoDocument({ data }: { data: MemoDocumentData }) {
  const sections = parseMemoSections(data.narrative);
  const subtitle = parseMemoSubtitle(data.narrative);
  const summaryKeyRisks = findSection(sections, "Summary & Key Risks");
  const borrowerBackground = findSection(sections, "Borrower Background");
  const financialAnalysis = findSection(sections, "Financial Analysis");
  const repaymentConsiderations = findSection(sections, "Repayment Considerations");
  const { ratiosMarkdown } = splitFinancialAnalysis(financialAnalysis);

  const generatedDate = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="print:my-0">
      <div className="mb-3 flex flex-wrap gap-2 print:hidden">
        <button
          type="button"
          onClick={handlePrint}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-950 shadow-sm"
        >
          Download PDF
        </button>
        <button
          type="button"
          onClick={() => handleDownloadMarkdown(data.narrative, data.filingId)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-950 shadow-sm"
        >
          Download Markdown
        </button>
      </div>

      <div className="memo-document rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8 print:rounded-none print:border-none print:p-0 print:shadow-none">
        <header className="border-b border-slate-300 pb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-800">
            Credit Review Memorandum
          </p>
          <h2 className="mt-1 font-serif text-2xl font-semibold text-slate-900">
            {data.company ?? "Unknown company"}
            {data.fiscalYear ? ` (FY${data.fiscalYear})` : ""}
          </h2>
          <p className="mt-2 text-xs text-slate-500">Generated {generatedDate}</p>
          {subtitle ? <p className="mt-1 text-xs italic text-slate-500">{subtitle}</p> : null}
        </header>

        <div className="font-serif text-[15px] leading-relaxed text-slate-800 sm:text-base">
          <section className="mt-6" style={{ pageBreakInside: "avoid" }}>
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
              1. Summary &amp; Key Risks
            </h3>
            <div className="mt-2 space-y-3">
              <InlineMarkdown text={summaryKeyRisks} />
            </div>
          </section>

          <section className="mt-6" style={{ pageBreakInside: "avoid" }}>
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
              2. Borrower Background
            </h3>
            <div className="mt-2 space-y-3">
              <InlineMarkdown text={borrowerBackground} />
            </div>
          </section>

          <section className="mt-6" style={{ pageBreakInside: "avoid" }}>
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
              3. Financial Analysis
            </h3>
            <div className="mt-3 overflow-x-auto" style={{ pageBreakInside: "avoid" }}>
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-300 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-3 font-medium">Figure</th>
                    <th className="py-2 pr-3 text-right font-medium">Value</th>
                    <th className="py-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(FIGURE_LABELS) as (keyof MemoFigures)[]).map((key) => {
                    const figure = data.figures[key];
                    const notDisclosed = figure.value === null;
                    return (
                      <tr key={key} className="border-b border-slate-100">
                        <td className="py-2 pr-3">{FIGURE_LABELS[key]}</td>
                        <td
                          className={`py-2 pr-3 text-right tabular-nums ${
                            notDisclosed ? "italic text-slate-400" : "text-slate-900"
                          }`}
                        >
                          {formatFigureValue(figure)}
                        </td>
                        <td className="py-2 text-xs text-slate-500">
                          {figure.page ? `page ${figure.page}, ${figure.section}` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Ratios</p>
              <InlineMarkdown text={ratiosMarkdown} />
            </div>
          </section>

          <section className="mt-6" style={{ pageBreakInside: "avoid" }}>
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
              4. Repayment Considerations
            </h3>
            <div className="mt-2 space-y-3">
              <InlineMarkdown text={repaymentConsiderations} />
            </div>
          </section>

          <section className="mt-6" style={{ pageBreakInside: "avoid" }}>
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
              5. Analyst-Input Sections
            </h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-500">
              <li>Loan structure &amp; pricing: [REQUIRES DEAL DATA]</li>
              <li>Collateral analysis: [REQUIRES DEAL DATA]</li>
              <li>Risk rating &amp; policy exceptions: [REQUIRES BANK POLICY + ANALYST JUDGMENT]</li>
            </ul>
          </section>

          <section className="mt-6 border-t border-slate-200 pt-4 text-sm">
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">6. Sources</h3>
            <ol className="mt-2 space-y-2 text-xs text-slate-600">
              {data.citations.map((citation, index) => (
                <li key={index} className="flex gap-2">
                  <span className="tabular-nums text-slate-400">{index + 1}.</span>
                  <span>
                    Page {citation.page ?? "n/a"}, {citation.section ?? "section n/a"}
                    {citation.snippet ? ` — ${citation.snippet}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <p className="mt-8 border-t border-slate-200 pt-3 text-[11px] text-slate-400 print:mt-6">
          Generated by CreditLens · {generatedDate} · {data.filingId}
        </p>
      </div>
    </div>
  );
}
