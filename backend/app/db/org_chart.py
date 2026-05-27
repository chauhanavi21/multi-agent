"""The locked org chart every company starts with.

Users CANNOT change this. Only `is_admin` users can mutate via /api/admin/template.

Note: the manager agent is NOT listed here — every company implicitly has a
manager as the supervisor. This template lists worker agents only.
"""

# The fixed structure: worker agent name -> count (only 1 of each for now).
DEFAULT_ORG_CHART = {
    "sales": 1,
    "dev_backend": 1,
    "dev_frontend": 1,
    "dev_qa": 1,
    "social_analyst": 1,
}


def get_locked_template() -> dict:
    """Return a copy so callers can't mutate the template."""
    return dict(DEFAULT_ORG_CHART)
