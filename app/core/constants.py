"""
app/core/constants.py
─────────────────────────────────────────────────────────────────────────────
Central string constants for status fields used across the platform.
Import these everywhere instead of using bare string literals.
─────────────────────────────────────────────────────────────────────────────
"""


class LeadStatus:
    """Possible values for the Lead.status column."""
    NEW        = "new"        # freshly discovered / imported, no outreach yet
    CONTACTED  = "contacted"  # at least one email has been sent
    FOLLOW_UP  = "follow_up"  # needs follow-up based on email thread or sales feedback
    QUALIFIED  = "qualified"  # sales team confirmed as a real prospect
    CONVERTED  = "converted"  # became a customer
    LOST       = "lost"       # not interested / unreachable


class EmailStatus:
    """Possible values for the OutreachEmail.status column."""
    DRAFT          = "draft"           # generated but not yet sent
    SENT           = "sent"            # successfully sent to the contact
    FOLLOW_UP_SENT = "follow_up_sent"  # follow-up email sent (3 days after initial)


class EmailType:
    """Distinguishes the type of outreach email."""
    INITIAL   = "initial"    # first-touch personalised email
    FOLLOW_UP = "follow_up"  # follow-up sent 3 days after initial with no response
