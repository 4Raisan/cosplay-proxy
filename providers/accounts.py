"""Cosplay — Account-based provider stubs.

Defines the list of providers that support OAuth / connected-account
authentication.  Phase 1 registers these as "Coming Soon" — actual
OAuth flows are deferred to a later phase.

The ACCOUNT_PROVIDERS list is the single source of truth.  To add a
new account-based provider, append an AccountProvider entry here.
The UI auto-renders from this list without code changes.
"""

from __future__ import annotations

from providers.models import AccountProvider

# ---------------------------------------------------------------------------
# Account provider registry
# ---------------------------------------------------------------------------

ACCOUNT_PROVIDERS: list[AccountProvider] = [
    AccountProvider(
        id="openai_chatgpt",
        name="OpenAI (ChatGPT)",
        description=(
            "Connect your ChatGPT Plus, Team, or Pro subscription. "
            "Uses your existing plan — no API key required."
        ),
        connected=False,
        coming_soon=False,
    ),
    # Future providers can be added here:
    # AccountProvider(
    #     id="google_ai",
    #     name="Google AI (Gemini)",
    #     description="Connect with your Google account.",
    #     connected=False,
    #     coming_soon=True,
    # ),
]


def get_account_providers() -> list[AccountProvider]:
    """Return all available account-based providers."""
    from providers.connected_accounts import get_openai_status
    
    providers = []
    for base in ACCOUNT_PROVIDERS:
        p = base.model_copy()
        if p.id == "openai_chatgpt":
            status = get_openai_status()
            p.connected = status.get("connected", False)
            if p.connected and "email" in status:
                p.account_email = status["email"]
        providers.append(p)
    return providers
