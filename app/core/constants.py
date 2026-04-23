"""
app/core/constants.py
─────────────────────────────────────────────────────────────────────────────
Central string constants for status fields used across the platform.
Import these everywhere instead of using bare string literals.
─────────────────────────────────────────────────────────────────────────────
"""

HUNTER_TARGET_DEPARTMENTS  = "management,operations,executive,sales"
HUNTER_TARGET_SENIORITY    = "senior,executive"
HUNTER_VERIFICATION_STATUS = "valid,accept_all"

HORECA_QUERY_MAP: dict[str, list[str]] = {
    # ── A. Bakery & Confectionery ──────────────────────────────────────────
    "Bakery":           ["bakeries in {city}", "cake shop {city}", "patisserie {city}"],
    # ── B. Dairy & Frozen ─────────────────────────────────────────────────
    "IceCream":         ["ice cream parlour {city}", "gelato shop {city}", "frozen dessert {city}"],
    # ── C. Beverage ───────────────────────────────────────────────────────
    "Beverage":         ["juice manufacturer {city}", "beverage company {city}", "syrup manufacturer {city}"],
    # ── D. HORECA ─────────────────────────────────────────────────────────
    "Restaurant":       ["restaurants in {city}", "fine dining {city}"],
    "Cafe":             ["cafes in {city}", "coffee shops {city}", "dessert cafe {city}"],
    # "Hotel":            ["hotels in {city}"],
    "Catering":         ["catering services {city}", "event caterers {city}"],
    "CloudKitchen":     ["cloud kitchen {city}", "dark kitchen {city}"],
    # ── E. Traditional Sweets ─────────────────────────────────────────────
    "Mithai":           ["sweet shop {city}", "mithai shop {city}", "halwai {city}"],
    # ── F. Food Processing ────────────────────────────────────────────────
    "FoodProcessing":   ["biscuit manufacturer {city}", "packaged food company {city}", "food processing unit {city}"],
    # ── G. Health / Organic / Jaggery ─────────────────────────────────────
    "Organic":          ["organic food brand {city}", "jaggery products {city}"],
    # ── H. Fermentation (Brewery / Distillery) ────────────────────────────
    "Brewery":          ["brewery {city}", "craft beer {city}"],
}

# HORECA_QUERY_MAP above controls which segments the weekly cron processes.
_FULL_QUERY_MAP: dict[str, list[str]] = {
    "Bakery":         ["bakeries in {city}", "cake shop {city}", "patisserie {city}"],
    "IceCream":       ["ice cream parlour {city}", "gelato shop {city}", "frozen dessert {city}"],
    "Beverage":       ["juice manufacturer {city}", "beverage company {city}", "syrup manufacturer {city}"],
    "Restaurant":     ["restaurants in {city}", "fine dining {city}"],
    "Cafe":           ["cafes in {city}", "coffee shops {city}", "dessert cafe {city}"],
    # "Hotel":          ["hotels in {city}"],
    "Catering":       ["catering services {city}", "event caterers {city}"],
    "CloudKitchen":   ["cloud kitchen {city}", "dark kitchen {city}"],
    "Mithai":         ["sweet shop {city}", "mithai shop {city}", "halwai {city}"],
    "FoodProcessing": ["biscuit manufacturer {city}", "packaged food company {city}", "food processing unit {city}"],
    "Organic":        ["organic food brand {city}", "jaggery products {city}"],
    "Brewery":        ["brewery {city}", "craft beer {city}"],
}

SEGMENT_WEIGHTS = {
    "Mithai":         100,
    "Bakery":         100,
    "FoodProcessing":  95,
    "IceCream":        90,
    "Beverage":        88,
    "Catering":        80,
    "Cafe":            78,
    "CloudKitchen":    72,
    "Organic":         70,
    "Brewery":         65,
    "Restaurant":      60,
    "Hotel":           55,
}

roles = [
        "Owner",
        # "Founder",
        # "Co-founder",
        # "Director",
        "Procurement Manager",
        "Purchase Manager",
        # "Purchase Head",
        "Supply Chain Manager",
        # "Supply Chain Head",
        "F&B Manager",
        # "F&B Director",
        # "Chef",
        # "Head of Supply Chain",
        # "Operations Manager",
        # "Operations Director",
        # "General Manager",
        # "Manager",
        # "Store Manager"
    ]


DECISION_MAKER_KEYWORDS = [
    "f&b", "food", "beverage", "procurement", "purchase", "supply",
    "operations", "founder", "owner", "director", "manager", "head",
    "executive", "ceo", "coo", "gm", "general manager",
]

DEPT_SCORE: dict[str, int] = {
    "executive":  100,
    "management":  90,
    "operations":  80,
    "sales":       70,
    "finance":     50,
    "support":     30,
}


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
    INITIAL   = "initial"    # first-touch personalized email
    FOLLOW_UP = "follow_up"  # follow-up sent 3 days after initial with no response

