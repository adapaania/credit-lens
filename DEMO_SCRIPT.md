# CreditLens — 10-Minute Demo Script

Timings are approximate targets, not hard cuts — pace to what feels natural when you're actually talking. Screen actions are in *italics*; what to say is plain text. Total run time: ~10 minutes.

---

## 1. Hook + problem (0:00 – 1:00)

*Screen: your face / title slide, no app yet.*

"Commercial credit analysts spend hours every time they evaluate a company — reading a hundred-plus-page SEC 10-K, copying numbers into a spreadsheet, hand-noting page numbers so they can prove where each figure came from, and reading the risk factors section by hand to catch anything that could affect repayment. Every one of those steps is manual, and every manual copy is a place a citation can quietly drift from its source.

I built CreditLens to fix that: an agentic RAG app where an analyst picks a filing, asks questions the way they'd ask a colleague, and gets back answers where every financial figure is cited to an exact page and section — not just a plausible-sounding number."

---

## 2. Live demo — cited Q&A (1:00 – 3:00)

*Screen: open the live app (credit-lens-teal.vercel.app). Boeing is selected by default.*

"Here's the live app. Boeing's 10-K is already loaded. Let me ask it a real question."

*Type: "What was Boeing's total consolidated revenue in fiscal year 2024?"*

"And there's the answer — $66,517 million — with a citation right in the text: page 36, the Revenues section. That's not the model guessing from training data. It actually pulled that chunk out of the filing I ingested, and if I tap the citation..."

*Tap the inline citation chip.*

"...it shows me the exact source text. That's the whole trust mechanism this app is built around — every number is traceable."

*Type a follow-up: "What liquidity risks did Boeing disclose?"*

"This one's qualitative, not a number — and it still comes back grounded in the actual Risk Factors section, not a generic answer about credit risk in general."

---

## 3. Live demo — memory + switching filings (3:00 – 4:15)

*Screen: switch the filing dropdown to Lockheed Martin.*

"Now let's switch filings — I'll pick Lockheed Martin — and ask a follow-up that references the earlier conversation."

*Type: "What were Lockheed Martin's net earnings in fiscal year 2024, and how does that compare to Boeing's revenue we just looked at?"*

"It remembers Boeing's number from earlier in the thread — that's a LangGraph agent with per-thread memory, not a stateless single-shot call — and it cites Lockheed's new figure independently. Different filing, same trust rules."

---

## 4. Live demo — refusal (cross-company guardrail) (4:15 – 5:15)

*Screen: keep Lockheed's filing selected.*

"Here's something that matters a lot for a credit tool specifically. I've got Lockheed's filing selected right now. Watch what happens if I ask about a different company."

*Type: "What was RTX's total debt at the end of fiscal year 2024?"*

"It declines and tells me to switch the filing selector — instead of answering from its own training data with a citation that's actually pointing at the wrong company's filing. Early in building this, that's exactly what it did: gave a real number, wrong-company citation, which is a worse failure than just being wrong, because it *looks* verified. Closing that leak was one of the three concrete fixes I'll get to in a minute."

---

## 5. Live demo — web search routing (5:15 – 6:15)

*Screen: ask something outside the filing's scope.*

"The agent has a second tool too — web search — for anything that isn't in the filing."

*Type: "What's the current interest rate environment doing to aerospace and defense company borrowing costs?"*

"It goes out to Tavily for this instead of guessing, and — this is the important part — it never presents that web result as if it were a number from the SEC filing. Filing data and web data stay clearly separated, every time."

---

## 6. Live demo — memo drafting (6:15 – 7:45)

*Screen: click "Draft memo section."*

"Last feature: one click turns the same retrieval pipeline into a structured credit memo."

*Click the button, wait for it to generate.*

"This is a risks-first memo — key risks and mitigants up front, then the financials supporting that argument, computed ratios, all with citations, and a sources list at the bottom. Nothing here is invented: if a figure isn't clearly stated in the filing, the memo says 'not disclosed' instead of guessing. And it exports to PDF for a real workflow — an analyst could actually hand this to a credit committee."

*Scroll to show the risks section, then the sources footer.*

---

## 7. What's under the hood (7:45 – 8:45)

*Screen: pull up the architecture diagram (or just talk over the app).*

"Quickly, how it's built: Next.js frontend on Vercel, FastAPI backend on Railway, a LangGraph agent with two tools — filing retrieval and web search — routed through OpenRouter so the model is swappable. Retrieval itself is hybrid: dense embeddings plus BM25 lexical search, fused with reciprocal rank fusion, then reranked with Cohere. And every filing figure has to come from that retrieval tool — never from the model's own memory — that's enforced in the system prompt, not just a convention."

---

## 8. The evals that got it there (8:45 – 9:45)

*Screen: show the comparison table from the write-up, or just talk.*

"None of this was assumed to work — it's measured. I started with naive dense retrieval and got 33% numeric accuracy on a hand-verified test set. Switching to hybrid retrieval roughly doubled that, to 67%. Then I found every remaining failure was the same pattern — current-assets and current-liabilities questions failing across every company — because raw questions are mostly filler words that dilute the retrieval signal against a terse balance-sheet row. Rewriting the query into a short keyword phrase before retrieval pushed accuracy to 83%.

That fix wasn't free, though — it also introduced one new wrong-but-confident answer, and I reported that honestly rather than just the headline number, because knowing exactly where a RAG system still fails is as important as knowing where it works."

---

## 9. Close (9:45 – 10:00)

*Screen: back to the app or your face.*

"That's CreditLens — cited, agent-routed, evaluated end to end, and live right now. Thanks for watching."

---

## Notes for recording

- Have the app open in one tab, Boeing selected, before you hit record — don't demo the initial page load.
- Type slowly enough that captions/viewers can read along; don't rush the citation-tap moment in section 2, it's the whole thesis of the product.
- If a live call is slow, that's fine to talk over — don't stop narrating while you wait for a response.
- Cut section 5 (web search) first if you're running long; it's the most skippable without losing the core narrative.
