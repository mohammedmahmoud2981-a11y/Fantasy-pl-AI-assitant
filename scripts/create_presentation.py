"""
FantasyIQ – Polished Project Presentation Generator
====================================================
Generates a professional PPTX presentation showcasing the FantasyIQ
AI-powered Fantasy Premier League analytics app.

Usage:
    py scripts/create_presentation.py

Output:
    d:/Fantasy project/FantasyIQ_Presentation.pptx
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT  = Path(r"d:\Fantasy project")
REPORTS  = PROJECT / "reports"
ASSETS   = Path(r"C:\Users\DUBAI STORE\.gemini\antigravity\brain"
                r"\c0b3a93d-7b37-4a6e-8900-ec5e6959fcc9")
OUTPUT   = PROJECT / "FantasyIQ_Presentation.pptx"

MOCKUPS = {
    "dashboard":  ASSETS / "mockup_dashboard_1795482314779.jpg",
    "players":    ASSETS / "mockup_players_1795481994257.jpg",
    "squad":      ASSETS / "mockup_squad_1795482704473.jpg",
    "transfers":  ASSETS / "mockup_transfers_1795482637828.jpg",
    "analytics":  ASSETS / "mockup_analytics_1795482169912.jpg",
    "built_with": ASSETS / "built_with_1795482313520.jpg",
    "title_card": ASSETS / "fantasy_iq_title_card_1795482880807.jpg",
}

# ── Brand Palette ────────────────────────────────────────────────────────
IVORY      = RGBColor(0xF4, 0xF3, 0xEE)
CHARCOAL   = RGBColor(0x23, 0x27, 0x24)
LIME       = RGBColor(0xBD, 0xEB, 0x43)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xAA, 0xAA, 0xAA)
DARK_GREEN = RGBColor(0x2D, 0x5A, 0x27)
SOFT_BLACK = RGBColor(0x1A, 0x1A, 0x1A)
CARD_BG    = RGBColor(0xF9, 0xF9, 0xF5)
ACCENT2    = RGBColor(0x34, 0x8C, 0x31)  # for positive indicators

# ── Slide dimensions: 16:9 widescreen ────────────────────────────────────
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# ── Load metrics ─────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

model_metrics   = load_json(REPORTS / "next_gw_model_metrics.json")
hp_metrics      = load_json(REPORTS / "high_potential_metrics.json")
profile_metrics = load_json(REPORTS / "player_profile_metrics.json")
rolling_eval    = load_json(REPORTS / "rolling_season_evaluation.json")
transfer_bt     = load_json(REPORTS / "transfer_policy_backtest.json")


# ═══════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════

def set_slide_bg(slide, color: RGBColor):
    """Fill the entire slide background with a solid color."""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_shape_fill(slide, left, top, width, height, color: RGBColor, corner_radius=0):
    """Add a filled rounded rectangle (card)."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    if corner_radius:
        shape.adjustments[0] = corner_radius
    return shape


def add_text_box(slide, left, top, width, height, text: str, *,
                 font_size=18, bold=False, color=CHARCOAL, align=PP_ALIGN.LEFT,
                 font_name="Calibri"):
    """Add a simple text box and return the shape."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = align
    return txBox


def add_multiline_text(slide, left, top, width, height, lines: list[tuple], *,
                       align=PP_ALIGN.LEFT, spacing=1.2):
    """Add multiple styled lines. Each line: (text, size, bold, color, font_name)."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, (text, size, bold, color, font_name) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.font.name = font_name
        p.alignment = align
        p.space_after = Pt(size * (spacing - 1))
    return txBox


def add_accent_bar(slide, left, top, width=Inches(1.5), height=Pt(6)):
    """Add a small lime accent bar."""
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = LIME
    bar.line.fill.background()
    return bar


def add_mockup_image(slide, key: str, left, top, height=Inches(5.2)):
    """Add a mockup image if it exists."""
    path = MOCKUPS.get(key)
    if path and path.exists():
        slide.shapes.add_picture(str(path), left, top, height=height)


def add_metric_card(slide, left, top, width, height,
                    value: str, label: str, sublabel: str = ""):
    """Add a rounded metric card with big value + label."""
    card = add_shape_fill(slide, left, top, width, height, CARD_BG, corner_radius=0.08)
    # value
    add_text_box(slide, left + Inches(0.3), top + Inches(0.25),
                 width - Inches(0.6), Inches(0.6), value,
                 font_size=28, bold=True, color=DARK_GREEN, align=PP_ALIGN.CENTER)
    # label
    add_text_box(slide, left + Inches(0.3), top + Inches(0.9),
                 width - Inches(0.6), Inches(0.5), label,
                 font_size=12, bold=False, color=CHARCOAL, align=PP_ALIGN.CENTER)
    if sublabel:
        add_text_box(slide, left + Inches(0.3), top + Inches(1.3),
                     width - Inches(0.6), Inches(0.4), sublabel,
                     font_size=10, bold=False, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


def add_bullet_points(slide, left, top, width, height,
                      items: list[str], font_size=14, color=CHARCOAL):
    """Add bullet-point list."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.name = "Calibri"
        p.space_after = Pt(6)
        p.level = 0


# ═══════════════════════════════════════════════════════════════════════
# BUILD PRESENTATION
# ═══════════════════════════════════════════════════════════════════════

prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
blank_layout = prs.slide_layouts[6]  # blank


# ─────────────────────────────────────────────────────────────────────
# SLIDE 1 — TITLE / COVER
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

# Left side: Branding
add_accent_bar(slide, Inches(1), Inches(1.5), width=Inches(2.0), height=Pt(8))

add_multiline_text(slide, Inches(1), Inches(1.9), Inches(5.5), Inches(3.5), [
    ("FantasyIQ", 48, True,  CHARCOAL, "Calibri"),
    ("AI-Powered Fantasy Premier League Analytics", 22, False, CHARCOAL, "Calibri"),
    ("", 12, False, CHARCOAL, "Calibri"),
    ("Smarter decisions for every Gameweek", 18, False, LIGHT_GRAY, "Calibri"),
])

# Tagline at bottom
add_text_box(slide, Inches(1), Inches(6.0), Inches(5), Inches(0.6),
             "Mobile App  ·  ML Predictions  ·  Squad Optimization",
             font_size=13, color=LIGHT_GRAY, align=PP_ALIGN.LEFT)

# Right side: Dashboard mockup
add_mockup_image(slide, "dashboard", Inches(7.5), Inches(0.8), height=Inches(5.8))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 2 — THE PROBLEM
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(1), Inches(0.8))
add_text_box(slide, Inches(1), Inches(1.1), Inches(11), Inches(0.7),
             "The Challenge", font_size=36, bold=True, color=CHARCOAL)

pain_points = [
    ("700+", "Premier League players to evaluate every Gameweek"),
    ("£100M", "budget with strict squad rules — 15 players, max 3 per club"),
    ("38", "Gameweeks of shifting form, injuries, and fixture swings"),
    ("∞", "Transfer combinations to compare under point-hit penalties"),
]

for i, (num, desc) in enumerate(pain_points):
    y = Inches(2.2) + i * Inches(1.15)
    # accent circle
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.2), y, Inches(0.7), Inches(0.7))
    circle.fill.solid()
    circle.fill.fore_color.rgb = LIME
    circle.line.fill.background()
    add_text_box(slide, Inches(1.2), y + Inches(0.1), Inches(0.7), Inches(0.5),
                 num, font_size=18, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)
    add_text_box(slide, Inches(2.2), y + Inches(0.1), Inches(8), Inches(0.5),
                 desc, font_size=18, color=CHARCOAL)

add_text_box(slide, Inches(1), Inches(6.5), Inches(11), Inches(0.5),
             "FPL managers need data-driven tools — not just gut feeling.",
             font_size=16, bold=True, color=DARK_GREEN, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 3 — THE SOLUTION
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(1), Inches(0.8))
add_text_box(slide, Inches(1), Inches(1.1), Inches(11), Inches(0.7),
             "Introducing FantasyIQ", font_size=36, bold=True, color=CHARCOAL)

add_text_box(slide, Inches(1), Inches(2.0), Inches(5.5), Inches(1.0),
             "A practical analytics assistant that combines machine-learning "
             "predictions with FPL rules and squad constraints — all in a "
             "clean, mobile-first interface.",
             font_size=16, color=CHARCOAL)

features = [
    ("📊", "Dashboard", "Gameweek overview with expected-points predictions"),
    ("🔍", "Player Explorer", "Position filters, form, price, ownership, High Potential badges"),
    ("⚽", "Squad Builder", "Tactical pitch, captain badges, budget optimizer"),
    ("🔄", "Transfer Planner", "Same-position replacements, projected gain, budget impact"),
    ("📈", "Analytics", "Player profiling with K-Means clustering & anomaly detection"),
]

for i, (icon, title, desc) in enumerate(features):
    y = Inches(3.2) + i * Inches(0.78)
    card = add_shape_fill(slide, Inches(1), y, Inches(5.5), Inches(0.68), CARD_BG, corner_radius=0.06)
    add_text_box(slide, Inches(1.2), y + Inches(0.08), Inches(0.4), Inches(0.5),
                 icon, font_size=20, align=PP_ALIGN.CENTER)
    add_text_box(slide, Inches(1.7), y + Inches(0.05), Inches(1.8), Inches(0.3),
                 title, font_size=15, bold=True, color=CHARCOAL)
    add_text_box(slide, Inches(1.7), y + Inches(0.35), Inches(4.5), Inches(0.3),
                 desc, font_size=11, color=LIGHT_GRAY)

# Right side mockup
add_mockup_image(slide, "dashboard", Inches(7.5), Inches(1.5), height=Inches(5.5))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 4 — DASHBOARD SCREEN
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(5), Inches(0.6),
             "Dashboard", font_size=32, bold=True, color=CHARCOAL)

add_bullet_points(slide, Inches(0.8), Inches(2.0), Inches(5.5), Inches(3.5), [
    "• Current Gameweek overview with match status",
    "• Expected Points (xP) predictions from FantasyIQ ML model",
    "• Top recommended players for the upcoming Gameweek",
    "• FPL official xP shown alongside FantasyIQ predictions",
    "• Quick access to squad builder and transfer planner",
    "• Data refreshes from the FPL API every 15 minutes",
], font_size=14)

add_text_box(slide, Inches(0.8), Inches(5.8), Inches(5.5), Inches(0.8),
             "API endpoint: GET /api/overview\n"
             "Returns current GW, next deadline, top players, and team summaries.",
             font_size=11, color=LIGHT_GRAY)

add_mockup_image(slide, "dashboard", Inches(7.2), Inches(0.6), height=Inches(6.2))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 5 — PLAYER EXPLORER SCREEN
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(5), Inches(0.6),
             "Player Explorer", font_size=32, bold=True, color=CHARCOAL)

add_bullet_points(slide, Inches(0.8), Inches(2.0), Inches(5.5), Inches(3.5), [
    "• Browse 700+ Premier League players with real-time data",
    "• Filter by position: GK, DEF, MID, FWD",
    "• View price (£M), ownership %, form rating, and xP",
    '• "High Potential" badge when probability ≥ 65%',
    "• Sort by predicted points, price, or form",
    "• Logistic Regression classifier behind the badge (ROC-AUC: 0.92)",
], font_size=14)

add_text_box(slide, Inches(0.8), Inches(5.8), Inches(5.5), Inches(0.8),
             "API endpoints: GET /api/players  |  GET /api/predictions\n"
             "High Potential threshold: position-relative 75th percentile.",
             font_size=11, color=LIGHT_GRAY)

add_mockup_image(slide, "players", Inches(7.2), Inches(0.6), height=Inches(6.2))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 6 — SQUAD BUILDER SCREEN
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(5), Inches(0.6),
             "Squad Builder", font_size=32, bold=True, color=CHARCOAL)

add_bullet_points(slide, Inches(0.8), Inches(2.0), Inches(5.5), Inches(3.5), [
    "• Builds an optimized 15-player squad within any budget (default £100M)",
    "• Enforces all FPL constraints: 2 GK, 5 DEF, 5 MID, 3 FWD",
    "• Max 3 players from any single club",
    "• Tactical pitch visualization with starting XI and separated bench",
    "• Captain and Vice-Captain selection badges",
    "• Budget slider for real-time re-optimization",
    "• Greedy optimizer maximizes total predicted xP",
], font_size=14)

add_text_box(slide, Inches(0.8), Inches(5.8), Inches(5.5), Inches(0.8),
             "API endpoint: GET /api/squad?budget=100\n"
             "Optimizer in fantasyiq/optimizer.py — greedy selection with constraints.",
             font_size=11, color=LIGHT_GRAY)

add_mockup_image(slide, "squad", Inches(7.2), Inches(0.6), height=Inches(6.2))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 7 — TRANSFER PLANNER SCREEN
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(5), Inches(0.6),
             "Transfer Planner", font_size=32, bold=True, color=CHARCOAL)

add_bullet_points(slide, Inches(0.8), Inches(2.0), Inches(5.5), Inches(3.5), [
    "• Select an outgoing player to see same-position replacements",
    "• Ranked by projected points gain after transfer",
    "• Shows budget impact (remaining bank after swap)",
    "• Hybrid recommendation: xP primary, collaborative tie-breaking",
    "• Multi-player transfer plans (up to 5 players) with hit cost",
    "• Respects 3-per-club constraint across the full squad",
], font_size=14)

add_text_box(slide, Inches(0.8), Inches(5.8), Inches(5.5), Inches(0.8),
             "API: GET /api/recommendations/transfers?player_id=…&budget=…\n"
             "Plan: GET /api/recommendations/plan?player_ids=…&squad_ids=…",
             font_size=11, color=LIGHT_GRAY)

add_mockup_image(slide, "transfers", Inches(7.2), Inches(0.6), height=Inches(6.2))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 8 — ANALYTICS & PLAYER PROFILES
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(5), Inches(0.6),
             "Analytics & Player Profiles", font_size=32, bold=True, color=CHARCOAL)

n_clusters = profile_metrics.get("clusters", 3)
anomaly_ct = profile_metrics.get("anomaly_count", 14)
silhouette = profile_metrics.get("silhouette_score", 0.355)
n_players  = profile_metrics.get("players", 441)

add_bullet_points(slide, Inches(0.8), Inches(2.0), Inches(5.5), Inches(2.0), [
    f"• K-Means clustering: {n_clusters} player archetypes from {n_players} players",
    f"• Silhouette score: {silhouette:.3f}",
    f"• Isolation Forest anomaly detection: {anomaly_ct} outliers flagged",
    "• Feature set: points, minutes, goals, assists, xG, xA, xGC, value",
    "• Descriptive end-of-season profiling — not a prediction or guarantee",
], font_size=14)

# Mini metric cards
add_metric_card(slide, Inches(0.8), Inches(4.5), Inches(2.4), Inches(1.7),
                str(n_clusters), "Player Clusters", "K-Means archetypes")
add_metric_card(slide, Inches(3.5), Inches(4.5), Inches(2.4), Inches(1.7),
                str(anomaly_ct), "Anomalies Detected", "Isolation Forest (3% contamination)")

add_mockup_image(slide, "analytics", Inches(7.2), Inches(0.6), height=Inches(6.2))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 9 — ML MODEL PERFORMANCE
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Model Performance — Next-GW Points Prediction", font_size=32, bold=True, color=CHARCOAL)

add_text_box(slide, Inches(0.8), Inches(1.9), Inches(11), Inches(0.5),
             "HistGradientBoostingRegressor  ·  47 features  ·  Temporal train/test split  ·  "
             "10 seasons of historical data (2016/17 – 2025/26)",
             font_size=13, color=LIGHT_GRAY)

# Final test metrics
ft = model_metrics["final_test"]["hist_gradient_boosting"]
bl = model_metrics["final_test"]["last_3_gameweeks_baseline"]

add_metric_card(slide, Inches(0.8), Inches(2.8), Inches(2.6), Inches(1.8),
                f"{ft['mae']:.4f}", "Model MAE", "Final test (2025/26)")
add_metric_card(slide, Inches(3.7), Inches(2.8), Inches(2.6), Inches(1.8),
                f"{ft['rmse']:.4f}", "Model RMSE", "Final test (2025/26)")
add_metric_card(slide, Inches(6.6), Inches(2.8), Inches(2.6), Inches(1.8),
                f"{ft['r2']:.4f}", "Model R²", "Final test (2025/26)")
add_metric_card(slide, Inches(9.5), Inches(2.8), Inches(2.6), Inches(1.8),
                f"{ft['rows']:,}", "Test Rows", "Season 2025/26")

# Baseline comparison
add_text_box(slide, Inches(0.8), Inches(5.0), Inches(11), Inches(0.4),
             "Baseline Comparison (Last-3-GW Average)", font_size=16, bold=True, color=CHARCOAL)

add_metric_card(slide, Inches(0.8), Inches(5.5), Inches(2.6), Inches(1.4),
                f"{bl['mae']:.4f}", "Baseline MAE", "")
add_metric_card(slide, Inches(3.7), Inches(5.5), Inches(2.6), Inches(1.4),
                f"{bl['rmse']:.4f}", "Baseline RMSE", "")
add_metric_card(slide, Inches(6.6), Inches(5.5), Inches(2.6), Inches(1.4),
                f"{bl['r2']:.4f}", "Baseline R²", "")

# Improvement note
mae_improvement = ((bl["mae"] - ft["mae"]) / bl["mae"]) * 100
add_text_box(slide, Inches(9.5), Inches(5.7), Inches(2.6), Inches(1.0),
             f"▲ {mae_improvement:.1f}% lower MAE\nthan the baseline",
             font_size=14, bold=True, color=DARK_GREEN, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 10 — ROLLING SEASON EVALUATION
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Rolling Season Evaluation", font_size=32, bold=True, color=CHARCOAL)

add_text_box(slide, Inches(0.8), Inches(1.9), Inches(11), Inches(0.5),
             "Expanding-window chronological evaluation across 4 consecutive seasons",
             font_size=14, color=LIGHT_GRAY)

folds = rolling_eval["folds"]
for i, fold in enumerate(folds):
    x = Inches(0.8) + i * Inches(3.0)
    y = Inches(2.8)
    season = fold["evaluation_season"]
    m_mae = fold["model"]["mae"]
    b_mae = fold["last_3_gameweeks_baseline"]["mae"]
    improved = fold["improved_mae"]
    n_train = len(fold["training_seasons"])

    card = add_shape_fill(slide, x, y, Inches(2.7), Inches(3.5), CARD_BG, corner_radius=0.06)

    add_text_box(slide, x + Inches(0.2), y + Inches(0.2), Inches(2.3), Inches(0.4),
                 f"Season {season}", font_size=16, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)
    add_text_box(slide, x + Inches(0.2), y + Inches(0.7), Inches(2.3), Inches(0.3),
                 f"Training: {n_train} seasons", font_size=11, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)

    add_text_box(slide, x + Inches(0.2), y + Inches(1.2), Inches(2.3), Inches(0.3),
                 f"Model MAE: {m_mae:.4f}", font_size=14, bold=True, color=DARK_GREEN, align=PP_ALIGN.CENTER)
    add_text_box(slide, x + Inches(0.2), y + Inches(1.6), Inches(2.3), Inches(0.3),
                 f"Baseline MAE: {b_mae:.4f}", font_size=14, color=CHARCOAL, align=PP_ALIGN.CENTER)

    status = "✓ Model wins" if improved else "✗ Baseline wins"
    s_color = DARK_GREEN if improved else RGBColor(0xCC, 0x33, 0x33)
    add_text_box(slide, x + Inches(0.2), y + Inches(2.2), Inches(2.3), Inches(0.3),
                 status, font_size=14, bold=True, color=s_color, align=PP_ALIGN.CENTER)

    imp = ((b_mae - m_mae) / b_mae) * 100
    add_text_box(slide, x + Inches(0.2), y + Inches(2.7), Inches(2.3), Inches(0.3),
                 f"▲ {imp:.1f}% MAE improvement", font_size=11, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)

# Summary
mean_m = rolling_eval["mean_model_mae"]
mean_b = rolling_eval["mean_baseline_mae"]
n_beat = rolling_eval["folds_beating_baseline"]
add_text_box(slide, Inches(0.8), Inches(6.6), Inches(11), Inches(0.5),
             f"Mean Model MAE: {mean_m:.4f}  |  Mean Baseline MAE: {mean_b:.4f}  |  "
             f"Model beat baseline in {n_beat}/{len(folds)} seasons",
             font_size=14, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 11 — HIGH POTENTIAL CLASSIFIER
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             'High Potential Classifier — "مرشح قوي"', font_size=32, bold=True, color=CHARCOAL)

add_text_box(slide, Inches(0.8), Inches(1.9), Inches(11), Inches(0.5),
             "Logistic Regression — identifies players likely to score above their position's "
             "75th percentile in the next Gameweek",
             font_size=14, color=LIGHT_GRAY)

hp_ft = hp_metrics["final_test"]["metrics"]
hp_vl = hp_metrics["validation"]["metrics"]

# Final test cards
metrics_data = [
    (f"{hp_ft['roc_auc']:.4f}", "ROC-AUC", "Final test"),
    (f"{hp_ft['precision_at_0_5']:.2%}", "Precision @0.5", "Final test"),
    (f"{hp_ft['recall_at_0_5']:.2%}", "Recall @0.5", "Final test"),
    (f"{hp_ft['f1_at_0_5']:.4f}", "F1 Score @0.5", "Final test"),
    (f"{hp_ft['average_precision']:.4f}", "Avg Precision", "Final test"),
]

for i, (val, lbl, sub) in enumerate(metrics_data):
    x = Inches(0.8) + i * Inches(2.4)
    add_metric_card(slide, x, Inches(2.8), Inches(2.1), Inches(1.7), val, lbl, sub)

# Thresholds
thresholds = hp_metrics["final_test"]["thresholds_by_position_points"]
thresh_text = "Position thresholds (75th pctl): " + ", ".join(
    f"{pos}: {pts} pts" for pos, pts in sorted(thresholds.items())
)
add_text_box(slide, Inches(0.8), Inches(5.0), Inches(11), Inches(0.4),
             thresh_text, font_size=12, color=LIGHT_GRAY, align=PP_ALIGN.LEFT)

add_text_box(slide, Inches(0.8), Inches(5.6), Inches(11), Inches(1.0),
             "⚠ The probability estimates the chance of reaching this historical threshold. "
             "It is not a calibrated probability of injury or guaranteed points. "
             "Badge shown at ≥ 65% probability.",
             font_size=12, color=LIGHT_GRAY)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 12 — SYSTEM ARCHITECTURE
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "System Architecture", font_size=32, bold=True, color=CHARCOAL)

# Architecture boxes
layers = [
    ("📱  Mobile App", "React Native + Expo + TypeScript\nAndroid · iOS · Web",
     Inches(0.8), Inches(2.3), Inches(3.3), LIME),
    ("⚡  REST API", "FastAPI + Python 3.11+\nCORS · Caching (15 min TTL) · Docker",
     Inches(4.6), Inches(2.3), Inches(3.8), RGBColor(0x90, 0xD0, 0x40)),
    ("🧠  ML Models", "scikit-learn · Pandas · NumPy\nHistGradientBoosting · LogisticRegression\nK-Means · Isolation Forest",
     Inches(8.9), Inches(2.3), Inches(3.6), RGBColor(0x60, 0xB0, 0x30)),
]

for emoji_title, desc, x, y, w, bg_color in layers:
    card = add_shape_fill(slide, x, y, w, Inches(2.5), bg_color, corner_radius=0.06)
    add_text_box(slide, x + Inches(0.3), y + Inches(0.2), w - Inches(0.6), Inches(0.5),
                 emoji_title, font_size=18, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)
    add_text_box(slide, x + Inches(0.3), y + Inches(0.8), w - Inches(0.6), Inches(1.5),
                 desc, font_size=12, color=SOFT_BLACK, align=PP_ALIGN.CENTER)

# Arrows between boxes
for ax in [Inches(4.1), Inches(8.5)]:
    arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, ax, Inches(3.3), Inches(0.5), Inches(0.4))
    arrow.fill.solid()
    arrow.fill.fore_color.rgb = CHARCOAL
    arrow.line.fill.background()

# Data flow
add_text_box(slide, Inches(0.8), Inches(5.2), Inches(11.5), Inches(0.5),
             "Data Flow:   FPL API  →  Backend Cache  →  Feature Engineering  →  ML Inference  →  Mobile UI",
             font_size=14, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)

# Key files
add_multiline_text(slide, Inches(0.8), Inches(5.9), Inches(11), Inches(1.3), [
    ("Key Source Files:", 14, True, CHARCOAL, "Calibri"),
    ("backend/main.py — FastAPI endpoints  |  fantasyiq/optimizer.py — Squad optimizer  |  "
     "fantasyiq/prediction.py — ML inference", 11, False, LIGHT_GRAY, "Consolas"),
    ("fantasyiq/recommender.py — Hybrid recommendations  |  fantasyiq/features.py — Feature engineering  |  "
     "fantasyiq/data.py — FPL data fetcher", 11, False, LIGHT_GRAY, "Consolas"),
])


# ─────────────────────────────────────────────────────────────────────
# SLIDE 13 — TECHNOLOGY STACK
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Technology Stack", font_size=32, bold=True, color=CHARCOAL)

tech_groups = [
    ("Backend & Data", [
        ("Python 3.11+", "Core language for backend and data workflows"),
        ("FastAPI", "High-performance async REST API framework"),
        ("Pandas & NumPy", "Data manipulation and numerical computation"),
        ("scikit-learn", "ML models: regression, classification, clustering"),
    ]),
    ("Mobile & Web", [
        ("React Native", "Cross-platform mobile framework"),
        ("Expo", "Build toolchain for Android, iOS, and Web"),
        ("TypeScript", "Type-safe frontend development"),
    ]),
    ("DevOps", [
        ("Docker", "Containerized API deployment"),
        ("GitHub Actions", "CI: linting, type checks on every push"),
        ("Render / AWS", "Cloud deployment options (documented, not required)"),
    ]),
]

col_x = [Inches(0.8), Inches(4.6), Inches(8.8)]
for gi, (group_title, techs) in enumerate(tech_groups):
    x = col_x[gi]
    add_text_box(slide, x, Inches(2.0), Inches(3.5), Inches(0.4),
                 group_title, font_size=18, bold=True, color=DARK_GREEN)

    for ti, (name, desc) in enumerate(techs):
        y = Inches(2.6) + ti * Inches(1.0)
        card = add_shape_fill(slide, x, y, Inches(3.5), Inches(0.85), CARD_BG, corner_radius=0.05)
        add_text_box(slide, x + Inches(0.2), y + Inches(0.08), Inches(3.1), Inches(0.35),
                     name, font_size=14, bold=True, color=CHARCOAL)
        add_text_box(slide, x + Inches(0.2), y + Inches(0.45), Inches(3.1), Inches(0.35),
                     desc, font_size=10, color=LIGHT_GRAY)

# Built-with mockup
add_mockup_image(slide, "built_with", Inches(4.2), Inches(5.4), height=Inches(1.8))


# ─────────────────────────────────────────────────────────────────────
# SLIDE 14 — API DOCUMENTATION
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "API Endpoints", font_size=32, bold=True, color=CHARCOAL)

endpoints = [
    ("GET", "/api/health",          "Server health check"),
    ("GET", "/api/overview",        "GW summary, top players, club map"),
    ("GET", "/api/players",         "Full player list with stats (limit param)"),
    ("GET", "/api/predictions",     "FantasyIQ ML predictions for next GW"),
    ("GET", "/api/squad",           "Optimized 15-player squad (budget param)"),
    ("GET", "/api/recommendations/transfers", "Same-position replacements with net gain"),
    ("GET", "/api/recommendations/plan",      "Multi-player transfer plan (up to 5)"),
    ("GET", "/api/analytics/player-profiles", "K-Means clusters & anomaly scores"),
]

headers = ["Method", "Endpoint", "Description"]
col_widths = [Inches(1.0), Inches(4.5), Inches(5.5)]
table_left = Inches(0.8)
table_top = Inches(2.0)

# Header row
for ci, (hdr, cw) in enumerate(zip(headers, col_widths)):
    x = table_left + sum(col_widths[:ci])
    card = add_shape_fill(slide, x, table_top, cw, Inches(0.5), CHARCOAL, corner_radius=0)
    add_text_box(slide, x + Inches(0.15), table_top + Inches(0.05), cw - Inches(0.3), Inches(0.4),
                 hdr, font_size=12, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

for ri, (method, ep, desc) in enumerate(endpoints):
    y = table_top + Inches(0.5) + ri * Inches(0.5)
    row_color = CARD_BG if ri % 2 == 0 else WHITE
    for ci, (val, cw) in enumerate(zip([method, ep, desc], col_widths)):
        x = table_left + sum(col_widths[:ci])
        card = add_shape_fill(slide, x, y, cw, Inches(0.5), row_color, corner_radius=0)
        font_name = "Consolas" if ci <= 1 else "Calibri"
        c = DARK_GREEN if ci == 0 else CHARCOAL
        add_text_box(slide, x + Inches(0.15), y + Inches(0.05), cw - Inches(0.3), Inches(0.4),
                     val, font_size=11, bold=(ci == 0), color=c, font_name=font_name)

add_text_box(slide, Inches(0.8), Inches(6.5), Inches(11), Inches(0.4),
             "Interactive docs available at: http://localhost:8000/docs  (Swagger UI)",
             font_size=12, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 15 — DATA PIPELINE
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Data & Training Pipeline", font_size=32, bold=True, color=CHARCOAL)

pipeline_steps = [
    ("1. Collect", "collect_training_data.py\nFetch 10 seasons of\nplayer gameweek data"),
    ("2. Features", "build_next_gw_features.py\n47 rolling & seasonal\nstatistical features"),
    ("3. Train", "train_all_models.py\nHistGBR + LogReg +\nK-Means + IsolationForest"),
    ("4. Evaluate", "evaluate_rolling_seasons.py\n4-fold expanding-window\nchronological validation"),
    ("5. Deploy", "Docker + FastAPI\nModels served via\n/api/predictions"),
]

for i, (title, desc) in enumerate(pipeline_steps):
    x = Inches(0.5) + i * Inches(2.5)
    y = Inches(2.5)
    card = add_shape_fill(slide, x, y, Inches(2.2), Inches(2.8), CARD_BG, corner_radius=0.06)

    # Step number circle
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.75), y - Inches(0.3), Inches(0.6), Inches(0.6))
    circle.fill.solid()
    circle.fill.fore_color.rgb = LIME
    circle.line.fill.background()
    add_text_box(slide, x + Inches(0.75), y - Inches(0.2), Inches(0.6), Inches(0.4),
                 title.split(".")[0] + ".", font_size=16, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)

    add_text_box(slide, x + Inches(0.2), y + Inches(0.4), Inches(1.8), Inches(0.4),
                 title, font_size=14, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)
    add_text_box(slide, x + Inches(0.15), y + Inches(0.9), Inches(1.9), Inches(1.6),
                 desc, font_size=10, color=LIGHT_GRAY, align=PP_ALIGN.CENTER, font_name="Consolas")

    # Arrow between steps
    if i < len(pipeline_steps) - 1:
        arrow = slide.shapes.add_shape(
            MSO_SHAPE.RIGHT_ARROW,
            x + Inches(2.2), Inches(3.7), Inches(0.3), Inches(0.3)
        )
        arrow.fill.solid()
        arrow.fill.fore_color.rgb = CHARCOAL
        arrow.line.fill.background()

# Data stats
add_text_box(slide, Inches(0.8), Inches(5.9), Inches(11), Inches(0.4),
             "Historical data: 2016/17 – 2026/27  |  "
             f"Final test: {ft['rows']:,} rows on 2025/26  |  "
             "Deployment model retrained through 2025/26",
             font_size=13, color=CHARCOAL, align=PP_ALIGN.CENTER)

add_text_box(slide, Inches(0.8), Inches(6.4), Inches(11), Inches(0.5),
             "Data stored in: data/processed/player_gameweeks.csv.gz",
             font_size=11, color=LIGHT_GRAY, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 16 — HONEST LIMITATIONS
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, WHITE)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Honest Assessment & Limitations", font_size=32, bold=True, color=CHARCOAL)

limitations = [
    "Predictions are estimates — never guaranteed outcomes",
    "Transfer backtest: simple policy lost 89 pts vs. hold strategy in 2025/26",
    "RL agent: 1,657 pts vs. 1,786 for hold — not used for automated decisions",
    "Hybrid recommender slightly below pure form-based ranking (3.55 vs. 3.70 avg pts)",
    "Collaborative Filtering: Precision@10 = 0.03, limited to 5% tie-breaking weight",
    "No real-time injury data, chip strategy, or captain differential modeling",
    "Current season (2026/27) is diagnostic only — excluded from training and test",
]

for i, lim in enumerate(limitations):
    y = Inches(2.2) + i * Inches(0.68)
    # warning icon
    warn_bg = add_shape_fill(slide, Inches(1.0), y, Inches(0.4), Inches(0.4),
                              RGBColor(0xFF, 0xED, 0xAA), corner_radius=0.15)
    add_text_box(slide, Inches(1.0), y - Inches(0.03), Inches(0.4), Inches(0.4),
                 "⚠", font_size=14, align=PP_ALIGN.CENTER)
    add_text_box(slide, Inches(1.6), y + Inches(0.02), Inches(10), Inches(0.4),
                 lim, font_size=13, color=CHARCOAL)

add_text_box(slide, Inches(0.8), Inches(6.8), Inches(11), Inches(0.4),
             "Transparency builds trust. FantasyIQ is a research prototype — treat all outputs as guidance.",
             font_size=13, bold=True, color=DARK_GREEN, align=PP_ALIGN.CENTER)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 17 — FUTURE ROADMAP
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

add_accent_bar(slide, Inches(0.8), Inches(0.8))
add_text_box(slide, Inches(0.8), Inches(1.1), Inches(11), Inches(0.6),
             "Future Roadmap", font_size=32, bold=True, color=CHARCOAL)

roadmap = [
    ("Near-term", [
        "Add fixture difficulty ratings to prediction features",
        "Improve RL agent with larger training window",
        "Collect more user picks for meaningful CF signal",
    ]),
    ("Medium-term", [
        "Chip strategy modeling (Wildcard, Bench Boost, Triple Captain)",
        "Captain differential analysis and risk/reward scoring",
        "Push notifications for deadline reminders and form alerts",
    ]),
    ("Long-term", [
        "Public cloud deployment with HTTPS API",
        "User accounts with personal squad tracking",
        "Expanded xG model with per-fixture difficulty weighting",
    ]),
]

for gi, (phase, items) in enumerate(roadmap):
    x = Inches(0.8) + gi * Inches(4.0)
    y = Inches(2.2)
    card = add_shape_fill(slide, x, y, Inches(3.6), Inches(4.2), CARD_BG, corner_radius=0.06)

    # Phase header
    header_bg = add_shape_fill(slide, x, y, Inches(3.6), Inches(0.6),
                                LIME if gi == 0 else RGBColor(0x90, 0xD0, 0x40) if gi == 1 else RGBColor(0x60, 0xB0, 0x30),
                                corner_radius=0)
    add_text_box(slide, x + Inches(0.3), y + Inches(0.1), Inches(3.0), Inches(0.4),
                 phase, font_size=16, bold=True, color=CHARCOAL, align=PP_ALIGN.CENTER)

    for ii, item in enumerate(items):
        iy = y + Inches(0.9) + ii * Inches(0.95)
        add_text_box(slide, x + Inches(0.3), iy, Inches(3.0), Inches(0.8),
                     f"→ {item}", font_size=12, color=CHARCOAL)


# ─────────────────────────────────────────────────────────────────────
# SLIDE 18 — CLOSING / CTA
# ─────────────────────────────────────────────────────────────────────
slide = prs.slides.add_slide(blank_layout)
set_slide_bg(slide, IVORY)

# Large centered title
add_multiline_text(slide, Inches(1), Inches(1.5), Inches(5.5), Inches(3.0), [
    ("FantasyIQ", 52, True,  CHARCOAL, "Calibri"),
    ("", 10, False, CHARCOAL, "Calibri"),
    ("Make your next FPL decision", 24, False, CHARCOAL, "Calibri"),
    ("with more insight.", 24, True, DARK_GREEN, "Calibri"),
])

add_accent_bar(slide, Inches(1), Inches(4.8), width=Inches(3.0), height=Pt(6))

add_multiline_text(slide, Inches(1), Inches(5.2), Inches(5.5), Inches(1.5), [
    ("AI-powered analytics  ·  ML predictions  ·  Squad optimization", 13, False, LIGHT_GRAY, "Calibri"),
    ("", 8, False, LIGHT_GRAY, "Calibri"),
    ("Built with Python · FastAPI · scikit-learn · React Native · Docker", 12, False, LIGHT_GRAY, "Calibri"),
])

# Right side: Dashboard mockup as hero
add_mockup_image(slide, "dashboard", Inches(7.5), Inches(0.8), height=Inches(5.8))


# ═══════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════
prs.save(str(OUTPUT))
print(f"\n✅ Presentation saved to: {OUTPUT}")
print(f"   Slides: {len(prs.slides)}")
print(f"   Format: 16:9 widescreen ({SLIDE_W} x {SLIDE_H})")
