"""Per-model pricing in USD per 1M tokens.

Direct Anthropic and Bedrock Claude models are priced the same per the
public Bedrock + Anthropic listings. Keep this table in sync when prices move.
"""

# (input_per_1m_usd, output_per_1m_usd)
PRICING = {
    # Local — Ollama
    "phi3:mini": (0.0, 0.0),
    "llama3.1:8b": (0.0, 0.0),
    "nomic-embed-text": (0.0, 0.0),

    # Anthropic direct
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),

    # Bedrock (same prices as direct; Bedrock model IDs are versioned)
    "anthropic.claude-haiku-4-5-20251001-v1:0": (1.0, 5.0),
    "anthropic.claude-sonnet-4-5-20250929-v1:0": (3.0, 15.0),
}


def calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_p, out_p = PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * in_p + (output_tokens / 1_000_000) * out_p


def is_local(model: str) -> bool:
    in_p, out_p = PRICING.get(model, (0.0, 0.0))
    return in_p == 0.0 and out_p == 0.0


def is_bedrock(model: str) -> bool:
    return model.startswith("anthropic.") or model.startswith("amazon.")
