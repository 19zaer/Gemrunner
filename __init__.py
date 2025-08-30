from . import gemini, openai, anthropic, perplexity

REGISTRY = {
    "google": gemini,
    "openai": openai,
    "anthropic": anthropic,
    "perplexity": perplexity
}

def get(provider_name: str):
    if provider_name not in REGISTRY:
        raise ValueError(f"Unknown provider: {provider_name}")
    return REGISTRY[provider_name]
