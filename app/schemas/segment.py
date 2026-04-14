"""
app/schemas/segment.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas and catalog data for Segment-related request bodies.
─────────────────────────────────────────────────────────────────────────────
"""
from pydantic import BaseModel


class SegmentCreate(BaseModel):
    key: str
    label: str = ""
    cluster: str = ""
    description: str = ""
    color: str = "#5C736A"
    priority: int = 1


class SegmentPriorityUpdate(BaseModel):
    priority: int


# ─── SEGMENT CATALOG (seeded once, toggled / re-prioritised by admin) ─────────

SEGMENT_CATALOG = [
    {"key": "Mithai",         "label": "Mithai / Sweets",  "cluster": "Traditional Sweets",     "color": "#A0522D", "description": "Mithai shops & sweet chains; highest sugar density per kg of product"},
    {"key": "Bakery",         "label": "Bakery",           "cluster": "Bakery & Confectionery",  "color": "#B85C38", "description": "Bakeries, patisseries & cake shops; 15–30% sugar per product batch"},
    {"key": "FoodProcessing", "label": "Food Processing",  "cluster": "Food Processing",         "color": "#7B6D47", "description": "Industrial food processors, packaged-food manufacturers"},
    {"key": "IceCream",       "label": "Ice Cream",        "cluster": "Dairy & Frozen",           "color": "#C4878A", "description": "Ice-cream parlours & dairy-frozen chains; 12–18% sugar in mix"},
    {"key": "Beverage",       "label": "Beverage",         "cluster": "Beverage",                "color": "#4A7FA5", "description": "Juice bars, RTD beverage makers & soft-drink producers"},
    {"key": "Catering",       "label": "Catering",         "cluster": "HORECA",                  "color": "#6B5E44", "description": "Event & bulk caterers; large per-event sugar volumes"},
    {"key": "Cafe",           "label": "Café",             "cluster": "HORECA",                  "color": "#8FA39A", "description": "Coffee shops & cafés; syrups, frappes, baked goods"},
    {"key": "CloudKitchen",   "label": "Cloud Kitchen",    "cluster": "HORECA",                  "color": "#D4956A", "description": "Delivery-only kitchens; high-throughput dessert menus"},
    {"key": "Organic",        "label": "Organic",          "cluster": "Health & Organic",         "color": "#5A8A3C", "description": "Organic food brands, health-food stores, natural sweetener buyers"},
    {"key": "Brewery",        "label": "Brewery",          "cluster": "Fermentation",             "color": "#7B4F72", "description": "Craft breweries & fermentation units; sucrose for fermentation"},
    {"key": "Restaurant",     "label": "Restaurant",       "cluster": "HORECA",                  "color": "#3D6B56", "description": "Full-service restaurants & dhabas; dessert & cooking sugar"},
    {"key": "Hotel",          "label": "Hotel",            "cluster": "HORECA",                  "color": "#662B01", "description": "Hotel F&B departments; multiple restaurant, pastry, banquet consumption"},
]
