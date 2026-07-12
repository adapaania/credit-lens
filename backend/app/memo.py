"""Phase 3: credit memo Financial Summary & Risk Factors section.

Pipeline: targeted per-figure retrieval -> structured-output extraction of
six key figures (each with its own page/section citation, null if not
disclosed) -> ratio computation from whatever figures are non-null ->
risk-factor retrieval -> a narrative generation call that is only allowed
to use the figures and excerpts it was actually given.
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.prompts import MEMO_EXTRACTION_PROMPT, MEMO_NARRATIVE_PROMPT
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

RISK_QUERY = "principal credit risks liquidity risk factors financial condition"


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


def _gather_figure_context(filing_id: str) -> tuple[list[RetrievedChunk], str | None, int | None]:
    """Retrieve chunks for every key figure, deduped, plus infer company/fiscal_year."""
    seen: dict[tuple, RetrievedChunk] = {}
    company: str | None = None
    fiscal_year: int | None = None
    for query in FIGURE_QUERIES.values():
        for chunk in retrieve(query, filing_id=filing_id, top_k=5):
            key = (chunk["page"], chunk["section"], chunk["text"])
            seen.setdefault(key, chunk)
            if company is None:
                company = chunk["company"]
                fiscal_year = chunk["fiscal_year"]
    return list(seen.values()), company, fiscal_year


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
            lines.append(f"- {label}: ${figure.value:,.0f} million (page {figure.page}, {figure.section})")
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


def generate_narrative(
    company: str | None,
    fiscal_year: int | None,
    figures: FinancialFigures,
    ratios: Ratios,
    risk_chunks: list[RetrievedChunk],
) -> str:
    user_prompt = (
        f"Company: {company or 'unknown'}\n"
        f"Fiscal year: {fiscal_year or 'unknown'}\n\n"
        f"Extracted figures (already verified against the filing):\n{_format_figures_for_prompt(figures)}\n\n"
        f"Computed ratios:\n{_format_ratios_for_prompt(ratios)}\n\n"
        f"Risk factor excerpts:\n{_format_context(risk_chunks)}\n\n"
        'Write the "Financial Summary & Risk Factors" section now.'
    )
    response = _get_model().invoke(
        [SystemMessage(content=MEMO_NARRATIVE_PROMPT), HumanMessage(content=user_prompt)]
    )
    return response.content or ""


def _find_snippet(chunks: list[RetrievedChunk], page: int | None, section: str | None) -> str:
    for chunk in chunks:
        if chunk["page"] == page and chunk["section"] == section:
            return chunk["text"][:300]
    return ""


def generate_memo(filing_id: str) -> MemoResult:
    figures, figure_chunks, company, fiscal_year = extract_figures(filing_id)
    ratios = compute_ratios(figures)
    risk_chunks = retrieve(RISK_QUERY, filing_id=filing_id, top_k=8)
    narrative = generate_narrative(company, fiscal_year, figures, ratios, risk_chunks)

    citations: list[Citation] = []
    seen_pages: set[tuple[int | None, str | None]] = set()
    for key in FIGURE_LABELS:
        figure: CitedFigure = getattr(figures, key)
        location = (figure.page, figure.section)
        if figure.value is not None and location not in seen_pages:
            seen_pages.add(location)
            citations.append(
                {
                    "page": figure.page,
                    "section": figure.section,
                    "snippet": _find_snippet(figure_chunks, figure.page, figure.section),
                }
            )
    for chunk in risk_chunks:
        location = (chunk["page"], chunk["section"])
        if location not in seen_pages:
            seen_pages.add(location)
            citations.append({"page": chunk["page"], "section": chunk["section"], "snippet": chunk["text"][:300]})

    return {
        "company": company,
        "fiscal_year": fiscal_year,
        "figures": {key: getattr(figures, key).model_dump() for key in FIGURE_LABELS},
        "ratios": ratios.model_dump(),
        "narrative": narrative,
        "citations": citations,
    }
