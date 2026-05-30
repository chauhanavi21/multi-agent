"""Per-model pricing in USD per 1M tokens.

Local models are zero-cost. Cloud prices are list prices and may change —
update this table when Anthropic does.
"""

# (input_per_1m_usd, output_per_1m_usd)
PRICING = {
    # Local — Ollama (free; we still track tokens for analytics)
    "phi3:mini": (0.0, 0.0),
    "llama3.1:8b": (0.0, 0.0),
    "nomic-embed-text": (0.0, 0.0),

    # Anthropic — list prices in USD per million tokens
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}


def calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD. Returns 0.0 for unknown / free models."""
    in_p, out_p = PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * in_p + (output_tokens / 1_000_000) * out_p


def is_local(model: str) -> bool:
    in_p, out_p = PRICING.get(model, (0.0, 0.0))
    return in_p == 0.0 and out_p == 0.0
