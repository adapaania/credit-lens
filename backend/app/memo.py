"""Credit review memorandum, risks-first (Nichols style) per MEMO_TEMPLATE.md.

Pipeline: targeted per-figure retrieval -> structured-output figure
extraction -> ratio computation (in code, never by the LLM) -> risk-factor +
MD&A retrieval -> structured-output risk/mitigant extraction (exactly 3-5,
each grounded in a citation) -> cash-flow retrieval -> narrative-sections
generation (summary, borrower background, ratio interpretations, repayment
considerations) -> deterministic template assembly in code. The LLM never
writes the Analyst-Input Sections or the Sources list - those are fixed
boilerplate / a deduplicated citation list assembled in code, so they can
never be fabricated.
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.prompts import (
    MEMO_EXTRACTION_PROMPT,
    MEMO_NARRATIVE_SECTIONS_PROMPT,
    MEMO_RISK_EXTRACTION_PROMPT,
)
from app.config import get_settings
from app.retrieval.dense import RetrievedChunk
from app.retrieval.hybrid import retrieve

FIGURE_QUERIES = {
    "revenue": "total revenue total revenues consolidated",
    "net_income": "net income net loss attributable to shareholders",
    "total_debt": "total debt short-term and long-term debt borrowings",
    "cash": "cash and cash equivalents",
    "current_assets": "total current assets",
    "current_liabilities": "total current liabilities",
}

FIGURE_LABELS = {
    "revenue": "Revenue",
    "net_income": "Net income",
    "total_debt": "Total debt",
    "cash": "Cash and cash equivalents",
    "current_assets": "Current assets",
    "current_liabilities": "Current liabilities",
}

RATIO_LABELS = {
    "current_ratio": "Current ratio (current assets / current liabilities)",
    "net_margin": "Net margin (net income / revenue)",
    "cash_to_debt": "Cash-to-debt ratio (cash / total debt)",
    "debt_to_revenue": "Debt-to-revenue ratio (total debt / revenue)",
}

RISK_FACTORS_QUERY = "risk factors litigation regulatory competition supply chain"
MDA_RISK_QUERY = "management discussion and analysis trends uncertainties challenges outlook"
BORROWER_BACKGROUND_QUERY = "business overview segments products services operations"
CASHFLOW_QUERY = "net cash provided used by operating activities cash flow from operations"

# Static, never LLM-generated - MEMO_TEMPLATE.md Section 5 requires these headers
# verbatim with no fabricated content, since deal-specific data doesn't exist yet.
ANALYST_INPUT_SECTIONS = """- Loan structure & pricing: [REQUIRES DEAL DATA]
- Collateral analysis: [REQUIRES DEAL DATA]
- Risk rating & policy exceptions: [REQUIRES BANK POLICY + ANALYST JUDGMENT]"""

FILING_METADATA = {
    "boeing-2024-10k": {"filing_name": "Boeing FY2024 Form 10-K", "accession_number": "0000012927-25-000015"},
    "lockheed-2024-10k": {
        "filing_name": "Lockheed Martin FY2024 Form 10-K",
        "accession_number": "0000936468-25-000009",
    },
    "rtx-2024-10k": {"filing_name": "RTX FY2024 Form 10-K", "accession_number": "0000101829-25-000005"},
}


class CitedFigure(BaseModel):
    value: float | None = Field(
        None, description="Value in millions of dollars. Null if not disclosed in the excerpts."
    )
    page: int | None = None
    section: str | None = None


class FinancialFigures(BaseModel):
    revenue: CitedFigure
    net_income: CitedFigure
    total_debt: CitedFigure
    cash: CitedFigure
    current_assets: CitedFigure
    current_liabilities: CitedFigure


class Ratios(BaseModel):
    current_ratio: float | None = None
    net_margin: float | None = None
    cash_to_debt: float | None = None
    debt_to_revenue: float | None = None


class Risk(BaseModel):
    risk: str = Field(description="A specific, borrower-specific risk statement grounded in a disclosure or ratio.")
    mitigant: str = Field(
        description='The disclosed mitigant/monitor, or exactly "No disclosed mitigant - flag for analyst."'
    )
    page: int | None = None
    section: str | None = None


class RiskAssessment(BaseModel):
    risks: list[Risk] = Field(min_length=3, max_length=5)
    omitted_note: str | None = Field(
        None, description="Set only if more than 5 material risks existed in the excerpts."
    )


class NarrativeSections(BaseModel):
    summary: str
    borrower_background: str
    current_ratio_interpretation: str
    net_margin_interpretation: str
    cash_to_debt_interpretation: str
    debt_to_revenue_interpretation: str
    repayment_considerations: str


class Citation(TypedDict):
    page: int
    section: str
    snippet: str


class MemoResult(TypedDict):
    company: str | None
    fiscal_year: int | None
    figures: dict
    ratios: dict
    narrative: str
    citations: list[Citation]


_model: ChatOpenAI | None = None


def _get_model() -> ChatOpenAI:
    global _model
    if _model is None:
        settings = get_settings()
        _model = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
        )
    return _model


def _format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n---\n\n".join(f"[page {c['page']}, section: {c['section']}]\n{c['text']}" for c in chunks)


def _dedupe_chunks(*chunk_lists: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: dict[tuple, RetrievedChunk] = {}
    for chunks in chunk_lists:
        for chunk in chunks:
            key = (chunk["page"], chunk["section"], chunk["text"])
            seen.setdefault(key, chunk)
    return list(seen.values())


def _gather_figure_context(filing_id: str) -> tuple[list[RetrievedChunk], str | None, int | None]:
    """Retrieve chunks for every key figure, deduped, plus infer company/fiscal_year."""
    company: str | None = None
    fiscal_year: int | None = None
    all_chunks: list[list[RetrievedChunk]] = []
    for query in FIGURE_QUERIES.values():
        chunks = retrieve(query, filing_id=filing_id, top_k=5)
        all_chunks.append(chunks)
        if company is None and chunks:
            company = chunks[0]["company"]
            fiscal_year = chunks[0]["fiscal_year"]
    return _dedupe_chunks(*all_chunks), company, fiscal_year


def extract_figures(filing_id: str) -> tuple[FinancialFigures, list[RetrievedChunk], str | None, int | None]:
    chunks, company, fiscal_year = _gather_figure_context(filing_id)
    context = _format_context(chunks)
    structured = _get_model().with_structured_output(FinancialFigures, method="function_calling")
    figures = structured.invoke(f"{MEMO_EXTRACTION_PROMPT}\n\n{context}")
    return figures, chunks, company, fiscal_year


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def compute_ratios(figures: FinancialFigures) -> Ratios:
    return Ratios(
        current_ratio=_safe_div(figures.current_assets.value, figures.current_liabilities.value),
        net_margin=_safe_div(figures.net_income.value, figures.revenue.value),
        cash_to_debt=_safe_div(figures.cash.value, figures.total_debt.value),
        debt_to_revenue=_safe_div(figures.total_debt.value, figures.revenue.value),
    )


def _format_figures_for_prompt(figures: FinancialFigures) -> str:
    lines = []
    for key, label in FIGURE_LABELS.items():
        figure: CitedFigure = getattr(figures, key)
        if figure.value is None:
            lines.append(f"- {label}: not disclosed in reviewed filings")
        else:
            lines.append(f"- {label}: {_format_dollar_millions(figure.value)} (page {figure.page}, {figure.section})")
    return "\n".join(lines)


def _format_ratios_for_prompt(ratios: Ratios) -> str:
    lines = []
    for key, label in RATIO_LABELS.items():
        value = getattr(ratios, key)
        if value is None:
            lines.append(f"- {label}: not computable (one or more required figures not disclosed)")
        else:
            lines.append(f"- {label}: {value:.2f}")
    return "\n".join(lines)


def _format_risks_for_prompt(risks: RiskAssessment) -> str:
    lines = []
    for risk in risks.risks:
        location = f"page {risk.page}, {risk.section}" if risk.page else "citation not available"
        lines.append(f"- Risk: {risk.risk} | Mitigant: {risk.mitigant} | {location}")
    return "\n".join(lines)


def gather_risk_context(filing_id: str) -> list[RetrievedChunk]:
    risk_factor_chunks = retrieve(RISK_FACTORS_QUERY, filing_id=filing_id, top_k=6)
    mda_chunks = retrieve(MDA_RISK_QUERY, filing_id=filing_id, top_k=6)
    return _dedupe_chunks(risk_factor_chunks, mda_chunks)


def extract_risks(risk_chunks: list[RetrievedChunk], figures: FinancialFigures, ratios: Ratios) -> RiskAssessment:
    context = (
        f"Extracted figures:\n{_format_figures_for_prompt(figures)}\n\n"
        f"Computed ratios:\n{_format_ratios_for_prompt(ratios)}\n\n"
        f"Risk Factors and MD&A excerpts:\n{_format_context(risk_chunks)}"
    )
    structured = _get_model().with_structured_output(RiskAssessment, method="function_calling")
    return structured.invoke(f"{MEMO_RISK_EXTRACTION_PROMPT}\n\n{context}")


def generate_narrative_sections(
    company: str | None,
    fiscal_year: int | None,
    figures: FinancialFigures,
    ratios: Ratios,
    risks: RiskAssessment,
    background_chunks: list[RetrievedChunk],
    cashflow_chunks: list[RetrievedChunk],
) -> NarrativeSections:
    user_prompt = (
        f"Company: {company or 'unknown'}\n"
        f"Fiscal year: {fiscal_year or 'unknown'}\n\n"
        f"Extracted figures:\n{_format_figures_for_prompt(figures)}\n\n"
        f"Computed ratios:\n{_format_ratios_for_prompt(ratios)}\n\n"
        f"Already-identified key risks:\n{_format_risks_for_prompt(risks)}\n\n"
        f"Borrower background excerpts:\n{_format_context(background_chunks)}\n\n"
        f"Cash flow excerpts:\n{_format_context(cashflow_chunks)}"
    )
    structured = _get_model().with_structured_output(NarrativeSections, method="function_calling")
    return structured.invoke(f"{MEMO_NARRATIVE_SECTIONS_PROMPT}\n\n{user_prompt}")


def _format_dollar_millions(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f} million"


def _figure_citation_line(key: str, figure: CitedFigure) -> str:
    label = FIGURE_LABELS[key]
    if figure.value is None:
        return f"| {label} | Not disclosed in reviewed filings | — |"
    return f"| {label} | {_format_dollar_millions(figure.value)} | page {figure.page}, {figure.section} |"


def _assemble_markdown(
    filing_id: str,
    company: str | None,
    fiscal_year: int | None,
    figures: FinancialFigures,
    ratios: Ratios,
    risks: RiskAssessment,
    sections: NarrativeSections,
    citations: list[Citation],
) -> str:
    meta = FILING_METADATA.get(filing_id, {"filing_name": filing_id, "accession_number": "unknown"})
    company_display = company or "Unknown company"
    fy_display = fiscal_year or "unknown"

    risk_lines = [f"- **Risk:** {r.risk} → **Mitigant/Monitor:** {r.mitigant}" for r in risks.risks]
    if risks.omitted_note:
        risk_lines.append(f"\n*{risks.omitted_note}*")

    figures_table = "\n".join(
        ["| Figure | Value | Source |", "|---|---|---|"]
        + [_figure_citation_line(key, getattr(figures, key)) for key in FIGURE_LABELS]
    )

    ratio_rows = [
        ("current_ratio", ratios.current_ratio, sections.current_ratio_interpretation),
        ("net_margin", ratios.net_margin, sections.net_margin_interpretation),
        ("cash_to_debt", ratios.cash_to_debt, sections.cash_to_debt_interpretation),
        ("debt_to_revenue", ratios.debt_to_revenue, sections.debt_to_revenue_interpretation),
    ]
    ratio_lines = []
    for key, value, interpretation in ratio_rows:
        value_display = f"{value:.2f}" if value is not None else "not computable"
        ratio_lines.append(f"- **{RATIO_LABELS[key]}**: {value_display} — {interpretation}")

    sources_lines = [f"- Page {c['page']}, {c['section']}" for c in citations]

    return f"""# CREDIT REVIEW MEMORANDUM — {company_display} (FY{fy_display})
*Generated by CreditLens from {meta['filing_name']}, accession number {meta['accession_number']}. Draft for analyst review — not a credit decision.*

## 1. Summary & Key Risks
{sections.summary}

{chr(10).join(risk_lines)}

## 2. Borrower Background
{sections.borrower_background}

## 3. Financial Analysis

{figures_table}

**Ratios**

{chr(10).join(ratio_lines)}

## 4. Repayment Considerations
{sections.repayment_considerations}

## 5. Analyst-Input Sections
{ANALYST_INPUT_SECTIONS}

## 6. Sources
{chr(10).join(sources_lines)}
"""


def generate_memo(filing_id: str) -> MemoResult:
    figures, figure_chunks, company, fiscal_year = extract_figures(filing_id)
    ratios = compute_ratios(figures)

    risk_chunks = gather_risk_context(filing_id)
    risks = extract_risks(risk_chunks, figures, ratios)

    background_chunks = retrieve(BORROWER_BACKGROUND_QUERY, filing_id=filing_id, top_k=5)
    cashflow_chunks = retrieve(CASHFLOW_QUERY, filing_id=filing_id, top_k=5)

    sections = generate_narrative_sections(
        company, fiscal_year, figures, ratios, risks, background_chunks, cashflow_chunks
    )

    citations: list[Citation] = []
    seen_locations: set[tuple[int | None, str | None]] = set()

    def _add_citation(page: int | None, section: str | None, chunks: list[RetrievedChunk]) -> None:
        location = (page, section)
        if page is None or location in seen_locations:
            return
        seen_locations.add(location)
        snippet = next((c["text"][:300] for c in chunks if c["page"] == page and c["section"] == section), "")
        citations.append({"page": page, "section": section, "snippet": snippet})

    for key in FIGURE_LABELS:
        figure: CitedFigure = getattr(figures, key)
        _add_citation(figure.page, figure.section, figure_chunks)
    for risk in risks.risks:
        _add_citation(risk.page, risk.section, risk_chunks)
    for chunk in background_chunks:
        _add_citation(chunk["page"], chunk["section"], background_chunks)
    for chunk in cashflow_chunks:
        _add_citation(chunk["page"], chunk["section"], cashflow_chunks)

    citations.sort(key=lambda c: c["page"] or 0)

    narrative = _assemble_markdown(filing_id, company, fiscal_year, figures, ratios, risks, sections, citations)

    return {
        "company": company,
        "fiscal_year": fiscal_year,
        "figures": {key: getattr(figures, key).model_dump() for key in FIGURE_LABELS},
        "ratios": ratios.model_dump(),
        "narrative": narrative,
        "citations": citations,
    }
