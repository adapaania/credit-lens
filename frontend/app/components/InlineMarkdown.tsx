// Minimal renderer for the small, controlled markdown subset the backend
// actually generates in memo prose: **bold** spans, "- " bullet lists, and
// a lone "*italic*" line (the risk-omission note). Deliberately not a full
// markdown parser/dependency - the input is fully controlled by our own
// backend/app/memo.py, not arbitrary user content.
import { Fragment, ReactNode } from "react";

function renderBold(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    )
  );
}

export default function InlineMarkdown({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/).filter((b) => b.trim());

  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim());
        const isBulletBlock = lines.length > 0 && lines.every((l) => l.trim().startsWith("-"));

        if (isBulletBlock) {
          return (
            <ul key={i} className="list-disc space-y-2 pl-5">
              {lines.map((line, j) => (
                <li key={j}>{renderBold(line.replace(/^-\s*/, ""))}</li>
              ))}
            </ul>
          );
        }

        const trimmed = block.trim();
        if (trimmed.startsWith("*") && trimmed.endsWith("*") && !trimmed.startsWith("**")) {
          return (
            <p key={i} className="italic text-slate-500">
              {trimmed.slice(1, -1)}
            </p>
          );
        }

        return <p key={i}>{renderBold(block)}</p>;
      })}
    </>
  );
}
