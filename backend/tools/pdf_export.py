"""
Blueprint PDF Export — xhtml2pdf (pisa) renderer.

xhtml2pdf HARD LIMITS to observe:
  - NO display:flex / display:grid  → use <table> for multi-column layouts
  - NO white-space:pre-wrap         → convert \\n to <br/> manually
  - NO position:fixed               → page numbers via @page counter
  - Floats work but are fragile     → prefer table-based layouts
  - Background colours on table cells require border-collapse:collapse
"""

import os
import html
import re
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_WORD_LEN = 40   # characters before a long word is force-broken
_MAX_PRE_LEN  = 60   # characters per line inside <pre> blocks

# Priority → CSS colour mapping (table cells, not flex badges)
_PRIORITY_COLORS: Dict[str, str] = {
    "must-have":    "#dc2626",   # red-600
    "should-have":  "#2563eb",   # blue-600
    "nice-to-have": "#6b7280",   # gray-500
    "high":         "#dc2626",
    "medium":       "#d97706",
    "low":          "#6b7280",
}

_SP_COLORS: Dict[int, str] = {
    1: "#10b981",   # emerald-500
    2: "#10b981",
    3: "#2563eb",   # blue-600
    5: "#d97706",   # amber-600
    8: "#dc2626",   # red-600
}

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _e(text: Any) -> str:
    """HTML-escape and coerce to str."""
    return html.escape(str(text)) if text is not None else ""


def _nl2br(text: Any) -> str:
    """Replace real newlines with <br/> so xhtml2pdf renders them."""
    return _e(text).replace("\n", "<br/>")


def _wrap_long_words(escaped: str, max_len: int, sep: str) -> str:
    """
    Force-break tokens that exceed max_len characters.
    Operates on already-escaped text; preserves existing HTML entities.
    """
    parts = re.split(r"(\s+)", escaped)
    out: List[str] = []
    for part in parts:
        if not part or part.isspace():
            out.append(part)
        elif len(part) > max_len:
            chunks = [part[i : i + max_len] for i in range(0, len(part), max_len)]
            out.append(sep.join(chunks))
        else:
            out.append(part)
    return "".join(out)


def clean(text: Any, max_len: int = _MAX_WORD_LEN) -> str:
    """Escape + break long words for inline HTML context."""
    return _wrap_long_words(_e(text), max_len, "<br/>")


def clean_pre(text: Any) -> str:
    """Escape + break long words + preserve newlines for code/pre blocks."""
    escaped = _e(text)
    broken  = _wrap_long_words(escaped, _MAX_PRE_LEN, "\n")
    return broken


# ---------------------------------------------------------------------------
# Micro-component helpers
# ---------------------------------------------------------------------------

def _priority_badge(priority: str) -> str:
    key   = priority.lower().strip()
    color = _PRIORITY_COLORS.get(key, "#6b7280")
    return (
        f'<span style="color:#ffffff; background-color:{color}; '
        f'padding:2px 6px; border-radius:3px; font-size:8pt; '
        f'font-weight:700; text-transform:uppercase;">'
        f"{clean(priority)}</span>"
    )


def _sp_badge(story_points: Any) -> str:
    try:
        sp    = int(story_points)
        color = _SP_COLORS.get(sp, "#6b7280")
    except (ValueError, TypeError):
        sp    = story_points
        color = "#6b7280"
    return (
        f'<span style="color:#ffffff; background-color:{color}; '
        f'padding:2px 5px; border-radius:3px; font-size:8pt; font-weight:700;">'
        f"{sp} SP</span>"
    )


def _ul(items: List[Any], max_len: int = 80) -> str:
    if not items:
        return "<p><em>None</em></p>"
    rows = "".join(f"<li>{clean(item, max_len)}</li>" for item in items)
    return f"<ul>{rows}</ul>"


def _two_col_table(left_title: str, left_items: List[str],
                   right_title: str, right_items: List[str]) -> str:
    """xhtml2pdf-safe two-column layout using a table instead of flexbox."""
    def _col(title: str, items: List[str]) -> str:
        rows = "".join(f"<li>{clean(i, 60)}</li>" for i in items) if items else "<li><em>None</em></li>"
        return (
            f'<td style="width:50%; vertical-align:top; '
            f'border:1px solid #e2e8f0; padding:10px;">'
            f'<p style="font-weight:700; font-size:10pt; '
            f'color:#1e293b; margin:0 0 6px 0; text-transform:uppercase;">'
            f"{_e(title)}</p>"
            f"<ul style='margin:0 0 0 16px; padding:0;'>{rows}</ul></td>"
        )

    return (
        '<table style="width:100%; border-collapse:collapse; margin-bottom:15px;">'
        f"<tr>{_col(left_title, left_items)}{_col(right_title, right_items)}</tr>"
        "</table>"
    )


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

_CSS = """
@page {
    size: letter;
    margin: 2cm 2cm 2.5cm 2cm;
}

body {
    font-family: Helvetica, Arial, sans-serif;
    color: #1a202c;
    line-height: 1.55;
    margin: 0; padding: 0;
    font-size: 11pt;
}

/* ── Cover ── */
.cover-title {
    font-size: 32pt; font-weight: 700; color: #0f172a;
    margin-bottom: 8px; word-break: break-word;
}
.cover-tag {
    font-size: 13pt; color: #64748b;
    margin-bottom: 4px; font-style: italic;
}
.cover-meta {
    font-size: 9pt; color: #94a3b8;
    font-family: 'Courier New', Courier, monospace;
}
.cover-rule {
    border: none; border-top: 3px solid #1e293b;
    margin: 20px 0 30px 0;
}
.cover-section-box {
    border: 1px solid #e2e8f0; padding: 12px 16px;
    margin-bottom: 10px; background-color: #f8fafc;
}
.cover-section-box h4 {
    margin: 0 0 6px 0; font-size: 10pt; color: #334155;
    text-transform: uppercase; letter-spacing: 0.5px;
}

/* ── Section headings ── */
h2 {
    font-size: 15pt; font-weight: 700; color: #ffffff;
    background-color: #1e293b;
    padding: 8px 14px; margin-top: 30px; margin-bottom: 14px;
    text-transform: uppercase; letter-spacing: 1px;
}
h3 {
    font-size: 11pt; font-weight: 700; color: #334155;
    margin-top: 18px; margin-bottom: 7px;
    border-bottom: 1px solid #e2e8f0; padding-bottom: 3px;
    text-transform: uppercase; letter-spacing: 0.5px;
}
p { margin: 0 0 10px 0; font-size: 11pt; }

/* ── Callouts ── */
.callout {
    background-color: #f8fafc; border-left: 4px solid #3b82f6;
    padding: 12px 14px; margin-bottom: 14px; border-radius: 0 4px 4px 0;
    font-size: 11pt;
}
.callout-green  { border-left-color: #10b981; background-color: #f0fdf4; }
.callout-red    { border-left-color: #ef4444; background-color: #fef2f2; }
.callout-amber  { border-left-color: #d97706; background-color: #fffbeb; }

/* ── Tables ── */
table {
    width: 100%; border-collapse: collapse;
    margin-bottom: 14px; font-size: 10pt;
}
th, td {
    border: 1px solid #e2e8f0; padding: 8px 10px;
    text-align: left; vertical-align: top;
}
th {
    background-color: #f1f5f9; font-weight: 700; color: #334155;
    text-transform: uppercase; font-size: 8.5pt; letter-spacing: 0.5px;
}
tr.alt { background-color: #fcfcfd; }

/* ── Code / pre ── */
code {
    font-family: 'Courier New', Courier, monospace;
    background-color: #f1f5f9; padding: 1px 4px;
    border-radius: 2px; font-size: 9pt; color: #be185d;
}
pre {
    font-family: 'Courier New', Courier, monospace;
    background-color: #0f172a; color: #e2e8f0;
    padding: 12px; border-radius: 4px;
    font-size: 9pt; margin-bottom: 14px;
    white-space: pre-wrap; word-wrap: break-word;
}

/* ── Email timeline ── */
.email-step {
    border-left: 3px solid #3b82f6;
    padding: 8px 0 8px 14px; margin-bottom: 14px;
}
.email-step-meta {
    font-size: 8.5pt; color: #64748b; margin-bottom: 4px;
}

/* ── Misc ── */
ul { margin: 0 0 12px 20px; padding: 0; font-size: 11pt; }
li { margin-bottom: 5px; }
.footer {
    margin-top: 40px; text-align: center;
    font-size: 8.5pt; color: #94a3b8;
    border-top: 1px solid #e2e8f0; padding-top: 12px;
}
.page-break { page-break-before: always; }
.label-chip {
    font-size: 8pt; background-color: #e2e8f0;
    color: #475569; padding: 1px 5px; border-radius: 3px;
    margin-right: 3px;
}
"""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_cover(startup_name: str, session_id: str,
                   advisor: Dict, market: Dict) -> str:
    verdict    = advisor.get("verdict", "N/A")
    risk       = advisor.get("risk_score", 0.0)
    tam        = market.get("tam_estimate", "N/A")
    today      = date.today().strftime("%B %d, %Y")
    risk_color = "#10b981" if risk <= 0.4 else ("#ef4444" if risk > 0.6 else "#d97706")

    return f"""
    <div style="min-height:580pt;">
      <div style="margin-bottom: 20px;">
        <p style="font-size:9pt; color:#94a3b8; text-transform:uppercase;
                  letter-spacing:2px; margin-bottom:4px;">Blueprint — AI Founder Package</p>
        <h1 class="cover-title">{clean(startup_name, 60)}</h1>
        <p class="cover-tag">Founder Orchestration Report</p>
        <p class="cover-meta">Session: {clean(session_id, 60)} &nbsp;|&nbsp; Generated: {today}</p>
      </div>

      <hr class="cover-rule"/>

      <table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
        <tr>
          <td style="width:50%; vertical-align:top; padding-right:10px;">
            <div class="cover-section-box">
              <h4>VC Verdict</h4>
              <p style="font-size:14pt; font-weight:700; color:#0f172a; margin:0;">
                {clean(verdict)}
              </p>
            </div>
          </td>
          <td style="width:50%; vertical-align:top; padding-left:10px;">
            <div class="cover-section-box">
              <h4>Risk Score</h4>
              <p style="font-size:14pt; font-weight:700;
                        color:{risk_color}; margin:0;">
                {risk:.2f} / 1.00
              </p>
            </div>
          </td>
        </tr>
      </table>

      <div class="cover-section-box">
        <h4>Market Opportunity</h4>
        <p style="margin:0; font-size:11pt;">{clean(tam, 100)}</p>
      </div>

      <div class="cover-section-box" style="margin-top:10px;">
        <h4>What's Inside</h4>
        <table style="width:100%; border:none; font-size:10pt;">
          <tr>
            <td style="border:none; padding:3px 6px;">1. Executive Summary</td>
            <td style="border:none; padding:3px 6px;">4. System Architecture</td>
          </tr>
          <tr>
            <td style="border:none; padding:3px 6px;">2. Market Intelligence</td>
            <td style="border:none; padding:3px 6px;">5. Delivery Plan &amp; Sprint Map</td>
          </tr>
          <tr>
            <td style="border:none; padding:3px 6px;">3. Product Requirements (PRD)</td>
            <td style="border:none; padding:3px 6px;">6. Go-To-Market Strategy</td>
          </tr>
        </table>
      </div>
    </div>
    """


def _section_advisor(advisor: Dict) -> str:
    risk       = advisor.get("risk_score", 0.0)
    risk_cls   = "callout-red" if risk > 0.6 else ("callout-green" if risk <= 0.4 else "callout-amber")
    red_flags  = advisor.get("red_flags", [])

    flags_html = ""
    if red_flags:
        flags_html = "<h3>Critical Risks</h3>" + _ul(red_flags, 80)

    return f"""
    <h2>1. Executive Summary</h2>
    <div class="callout {risk_cls}">
      <table style="width:100%; border:none;">
        <tr>
          <td style="border:none; width:50%; vertical-align:top; padding:0 12px 0 0;">
            <strong style="font-size:9pt; text-transform:uppercase;
                           color:#64748b;">Verdict</strong><br/>
            <span style="font-size:13pt; font-weight:700; color:#0f172a;">
              {clean(advisor.get("verdict", "N/A"))}
            </span>
          </td>
          <td style="border:none; width:50%; vertical-align:top; padding:0;">
            <strong style="font-size:9pt; text-transform:uppercase;
                           color:#64748b;">Risk Score</strong><br/>
            <span style="font-size:13pt; font-weight:700; color:#0f172a;">
              {risk:.2f} / 1.00
            </span>
          </td>
        </tr>
      </table>
    </div>
    <h3>Advisor Reasoning</h3>
    <p>{clean(advisor.get("reasoning", "N/A"), 100)}</p>
    {flags_html}
    """


def _section_market(market: Dict) -> str:
    swot        = market.get("swot", {})
    competitors = market.get("competitors", [])
    trends      = market.get("trends", [])
    gaps        = market.get("gaps", [])
    sources     = market.get("sources", [])

    # SWOT — two-column table (xhtml2pdf-safe, NO flex)
    swot_html = ""
    if swot:
        swot_html = "<h3>SWOT Analysis</h3>"
        swot_html += _two_col_table(
            "Strengths",    swot.get("strengths", []),
            "Weaknesses",   swot.get("weaknesses", []),
        )
        swot_html += _two_col_table(
            "Opportunities", swot.get("opportunities", []),
            "Threats",       swot.get("threats", []),
        )

    # Competitors
    comp_html = ""
    if competitors:
        rows = ""
        for i, comp in enumerate(competitors):
            row_cls = ' class="alt"' if i % 2 else ""
            rows += (
                f"<tr{row_cls}>"
                f"<td><strong>{clean(comp.get('name',''), 30)}</strong></td>"
                f"<td>{clean(comp.get('description',''), 80)}</td>"
                f"<td style='font-size:9pt; color:#3b82f6;'>"
                f"{clean(comp.get('url',''), 40)}</td>"
                f"</tr>"
            )
        comp_html = (
            "<h3>Competitor Landscape</h3>"
            "<table><tr>"
            "<th style='width:18%;'>Company</th>"
            "<th style='width:62%;'>Analysis (Core Strength → Exploitable Weakness)</th>"
            "<th style='width:20%;'>URL</th>"
            f"</tr>{rows}</table>"
        )

    # Trends
    trends_html = ""
    if trends:
        trends_html = "<h3>Market Trends (Why Now)</h3>" + _ul(trends, 90)

    # Gaps
    gaps_html = ""
    if gaps:
        gaps_html = "<h3>Monetisable Market Gaps</h3>" + _ul(gaps, 90)

    # Sources
    sources_html = ""
    if sources:
        items = "".join(
            f"<li><span style='font-size:9pt; color:#3b82f6;'>"
            f"{clean(s, 80)}</span></li>"
            for s in sources
        )
        sources_html = f"<h3>Research Sources</h3><ul>{items}</ul>"

    return f"""
    <div class="page-break"></div>
    <h2>2. Market Intelligence</h2>
    <div class="callout callout-green">
      <strong>Total Addressable Market</strong><br/>
      <span style="font-size:12pt; font-weight:700; color:#0f172a;">
        {clean(market.get("tam_estimate", "N/A"), 100)}
      </span>
    </div>
    {swot_html}
    {comp_html}
    {trends_html}
    {gaps_html}
    {sources_html}
    """


def _section_prd(prd: Dict) -> str:
    goals    = prd.get("goals", [])
    metrics  = prd.get("success_metrics", [])
    stories  = prd.get("user_stories", [])
    features = prd.get("features", [])
    phases   = prd.get("roadmap_phases", [])

    # Success metrics — numbered, styled
    metrics_html = ""
    if metrics:
        _labels = ["North Star", "Activation", "Business"]
        rows = ""
        for idx, m in enumerate(metrics):
            label = _labels[idx] if idx < len(_labels) else f"Metric {idx+1}"
            rows += (
                f"<tr{'  class=\"alt\"' if idx % 2 else ''}>"
                f"<td style='width:18%; font-weight:700; font-size:9pt; "
                f"color:#1e293b;'>{label}</td>"
                f"<td>{clean(m, 90)}</td></tr>"
            )
        metrics_html = (
            "<h3>Success Metrics</h3>"
            "<table><tr><th>Type</th><th>Metric</th></tr>"
            f"{rows}</table>"
        )

    # Features table with colour-coded priority
    feat_html = ""
    if features:
        rows = ""
        for i, feat in enumerate(features):
            rows += (
                f"<tr{'  class=\"alt\"' if i % 2 else ''}>"
                f"<td style='width:15%;'>{_priority_badge(feat.get('priority','Medium'))}</td>"
                f"<td style='width:28%;'><strong>{clean(feat.get('name',''), 40)}</strong></td>"
                f"<td>{clean(feat.get('description',''), 70)}</td>"
                f"</tr>"
            )
        feat_html = (
            "<h3>MVP Feature Scope (MoSCoW)</h3>"
            "<table><tr><th>Priority</th><th>Feature</th><th>Description</th></tr>"
            f"{rows}</table>"
        )

    # Roadmap
    phase_html = ""
    if phases:
        rows = ""
        for i, ph in enumerate(phases):
            items_str = clean(", ".join(ph.get("items", [])), 80)
            goal_str  = clean(ph.get("goal", ""), 80)
            goal_cell = f"<br/><em style='font-size:9pt;color:#64748b;'>Goal: {goal_str}</em>" if goal_str else ""
            rows += (
                f"<tr{'  class=\"alt\"' if i % 2 else ''}>"
                f"<td style='width:28%;'><strong>{clean(ph.get('name',''), 40)}</strong>"
                f"{goal_cell}</td>"
                f"<td>{items_str}</td></tr>"
            )
        phase_html = (
            "<h3>Roadmap Phases</h3>"
            "<table><tr><th>Phase</th><th>Key Deliverables</th></tr>"
            f"{rows}</table>"
        )

    return f"""
    <div class="page-break"></div>
    <h2>3. Product Requirements Document (PRD)</h2>
    <h3>Problem Statement</h3>
    <div class="callout">
      <p style="margin:0;">{clean(prd.get("problem_statement","N/A"), 100)}</p>
    </div>
    <h3>Strategic Goals</h3>
    {_ul(goals, 90)}
    {metrics_html}
    <h3>Core User Stories (JTBD Format)</h3>
    {_ul(stories, 90)}
    {feat_html}
    {phase_html}
    """


def _section_architect(arch: Dict) -> str:
    endpoints    = arch.get("api_endpoints", [])
    design_notes = arch.get("system_design_notes", "N/A")
    sql          = arch.get("db_schema_sql", "")

    # API endpoints with auth column
    ep_html = ""
    if endpoints:
        rows = ""
        for i, ep in enumerate(endpoints):
            auth_val  = ep.get("auth_required", False)
            auth_cell = (
                '<span style="color:#10b981; font-weight:700;">✓ Yes</span>'
                if auth_val
                else '<span style="color:#6b7280;">No</span>'
            )
            resp = clean(ep.get("response_codes", ep.get("description", "")), 60)
            rows += (
                f"<tr{'  class=\"alt\"' if i % 2 else ''}>"
                f"<td style='width:8%;'><code>{clean(ep.get('method','GET'))}</code></td>"
                f"<td style='width:30%;'><strong>{clean(ep.get('path',''), 40)}</strong></td>"
                f"<td style='width:47%;'>{resp}</td>"
                f"<td style='width:15%; text-align:center;'>{auth_cell}</td>"
                f"</tr>"
            )
        ep_html = (
            "<h3>API Endpoints Contract</h3>"
            "<table><tr>"
            "<th>Method</th><th>Path</th><th>Description / Response Codes</th><th>Auth</th>"
            f"</tr>{rows}</table>"
        )

    sql_html = ""
    if sql:
        sql_html = (
            "<h3>Database Schema (PostgreSQL DDL)</h3>"
            f"<pre>{clean_pre(sql)}</pre>"
        )

    return f"""
    <div class="page-break"></div>
    <h2>4. System Architecture</h2>
    <h3>Design Notes &amp; Tech Stack</h3>
    <div class="callout callout-amber">
      <p style="margin:0;">{clean(design_notes, 100)}</p>
    </div>
    {ep_html}
    {sql_html}
    """


def _section_em(em: Dict) -> str:
    sprints   = em.get("sprints", [])
    issues    = em.get("issues", [])
    dod       = em.get("definition_of_done", [])
    debt      = em.get("tech_debt_risks", [])
    team_size = em.get("team_size_recommended", "N/A")

    # Build issue lookup for story-points decoration
    issue_map: Dict[str, Dict] = {iss.get("title", ""): iss for iss in issues}

    # Sprint cards
    sprint_html = ""
    for sp in sprints:
        sp_name  = sp.get("name", "Sprint")
        sp_goal  = sp.get("goal", "")
        goal_html = (
            f'<p style="font-style:italic; color:#64748b; font-size:10pt; margin:0 0 8px 0;">'
            f"Goal: {clean(sp_goal, 100)}</p>"
            if sp_goal else ""
        )
        rows = ""
        for title in sp.get("issue_titles", []):
            iss = issue_map.get(title, {})
            sp_val = iss.get("story_points", "?")
            rows += (
                f"<tr><td><strong>{clean(title, 70)}</strong></td>"
                f"<td style='text-align:center; width:10%;'>{_sp_badge(sp_val)}</td></tr>"
            )
        sprint_html += (
            f"<h3>{clean(sp_name, 60)}</h3>"
            f"{goal_html}"
            f"<table style='margin-bottom:6px;'>"
            f"<tr><th>Issue</th><th>Points</th></tr>"
            f"{rows}</table>"
        )

    # Issue details
    issue_detail_html = ""
    if issues:
        issue_detail_html = "<h3>Issue Details (GitHub-Ready)</h3>"
        for iss in issues:
            sp_val = iss.get("story_points", 3)
            labels = iss.get("labels", [])
            label_chips = "".join(
                f'<span class="label-chip">{clean(l)}</span>' for l in labels
            )
            body_html = _nl2br(iss.get("body", ""))
            issue_detail_html += (
                f'<div style="border:1px solid #e2e8f0; padding:10px; '
                f'margin-bottom:10px; background-color:#f8fafc;">'
                f'<p style="margin:0 0 4px 0; font-weight:700; font-size:10pt;">'
                f"{clean(iss.get('title',''), 70)} &nbsp; {_sp_badge(sp_val)}</p>"
                f'<p style="margin:0 0 6px 0; font-size:9pt;">{label_chips}</p>'
                f'<p style="margin:0; font-size:10pt; color:#334155;">{body_html}</p>'
                f"</div>"
            )

    dod_html  = ("<h3>Definition of Done</h3>" + _ul(dod, 90))  if dod  else ""
    debt_html = ("<h3>Tech Debt Risks</h3>"     + _ul(debt, 90)) if debt else ""

    return f"""
    <div class="page-break"></div>
    <h2>5. Delivery Plan</h2>
    <p><strong>Recommended Team:</strong> {clean(team_size, 60)}</p>
    {sprint_html}
    {issue_detail_html}
    {dod_html}
    {debt_html}
    """


def _section_marketing(mkt: Dict) -> str:
    pricing   = mkt.get("pricing_tiers", [])
    email_seq = mkt.get("email_sequence", [])
    plan_90   = mkt.get("ninety_day_plan", [])
    channels  = mkt.get("launch_channels", [])

    # Landing copy — split on pipe separator written by the upgraded prompt
    landing_raw = mkt.get("landing_copy", "N/A")
    landing_html = _nl2br(landing_raw)

    # Email campaign (single email block)
    campaign_raw = mkt.get("email_campaign", "")
    campaign_html = ""
    if campaign_raw:
        campaign_html = (
            "<h3>Launch Email</h3>"
            f'<div class="callout">'
            f'<p style="margin:0;">{_nl2br(campaign_raw)}</p>'
            f"</div>"
        )

    # LinkedIn post
    linkedin_raw  = mkt.get("linkedin_post", "")
    linkedin_html = ""
    if linkedin_raw:
        linkedin_html = (
            "<h3>LinkedIn Launch Post</h3>"
            f'<div class="callout">'
            f'<p style="margin:0;">{_nl2br(linkedin_raw)}</p>'
            f"</div>"
        )

    # Pricing — two-column table (NO flex)
    pricing_html = ""
    if pricing:
        cols = ""
        for tier in pricing:
            feats = "".join(
                f"<li>{clean(f, 50)}</li>" for f in tier.get("features", [])
            )
            price_str = clean(tier.get("price", "N/A"), 30)
            model_str = clean(tier.get("model", "Tier"), 20)
            recommended = tier.get("recommended", False)
            badge = (
                ' &nbsp;<span style="font-size:8pt; background-color:#10b981; '
                'color:#fff; padding:1px 5px; border-radius:3px;">RECOMMENDED</span>'
                if recommended else ""
            )
            cols += (
                f"<td style='width:50%; vertical-align:top; "
                f"border:1px solid #e2e8f0; padding:12px;'>"
                f"<p style='font-size:12pt; font-weight:700; color:#0f172a; margin:0 0 2px 0;'>"
                f"{model_str}{badge}</p>"
                f"<p style='font-size:10pt; color:#64748b; margin:0 0 8px 0;'>{price_str}</p>"
                f"<ul style='margin:0 0 0 16px; font-size:10pt;'>{feats}</ul>"
                f"</td>"
            )
        pricing_html = (
            "<h3>Pricing Strategy</h3>"
            "<table style='border-collapse:collapse; width:100%;'>"
            f"<tr>{cols}</tr></table>"
        )

    # Email drip timeline
    drip_html = ""
    if email_seq:
        drip_html = "<h3>Email Drip Campaign (5-Touch Sequence)</h3>"
        for step in email_seq:
            drip_html += (
                f'<div class="email-step">'
                f'<p style="font-weight:700; font-size:10.5pt; margin:0 0 2px 0;">'
                f"{clean(step.get('subject','No Subject'), 70)}</p>"
                f'<p class="email-step-meta">'
                f"Send: <strong>{clean(step.get('send_day',''), 20)}</strong>"
                f" &nbsp;|&nbsp; Goal: {clean(step.get('goal',''), 50)}</p>"
                f'<p style="margin:0; font-size:10pt;">{_nl2br(step.get("body",""))}</p>'
                f"</div>"
            )

    # 90-day plan
    plan_html = ""
    if plan_90:
        plan_html = "<h3>90-Day Launch Plan</h3>" + _ul(plan_90, 90)

    # Launch channels (with success_metric column from upgraded prompt)
    channels_html = ""
    if channels:
        rows = ""
        for i, ch in enumerate(channels):
            sm = clean(ch.get("success_metric", ch.get("expected_reach", "")), 40)
            rows += (
                f"<tr{'  class=\"alt\"' if i % 2 else ''}>"
                f"<td style='width:15%;'><strong>{clean(ch.get('channel',''), 20)}</strong></td>"
                f"<td style='width:55%;'>{clean(ch.get('tactic',''), 80)}</td>"
                f"<td style='width:15%;'>{clean(ch.get('expected_reach',''), 30)}</td>"
                f"<td style='width:15%;'>{sm}</td>"
                f"</tr>"
            )
        channels_html = (
            "<h3>Launch Channels</h3>"
            "<table><tr>"
            "<th>Channel</th><th>Tactic</th><th>Expected Reach</th><th>Success Metric</th>"
            f"</tr>{rows}</table>"
        )

    return f"""
    <div class="page-break"></div>
    <h2>6. Go-To-Market Strategy</h2>
    <h3>Landing Page Copy</h3>
    <div class="callout callout-green">
      <p style="margin:0; font-size:11pt;">{landing_html}</p>
    </div>
    {campaign_html}
    {linkedin_html}
    {pricing_html}
    {drip_html}
    {plan_html}
    {channels_html}
    """


# ---------------------------------------------------------------------------
# Main HTML assembler
# ---------------------------------------------------------------------------

def generate_report_html(
    startup_name: str,
    session_id: str,
    artifacts: Dict[str, Any],
) -> str:
    """
    Assemble a full founder-package HTML string ready for xhtml2pdf rendering.

    All multi-column layouts use <table> — NOT display:flex — because
    xhtml2pdf/ReportLab does not support CSS flexbox.
    Newlines in LLM output are converted to <br/> via _nl2br().
    """
    advisor = artifacts.get("startup_advisor", {})
    market  = artifacts.get("market_research", {})
    prd     = artifacts.get("product_manager", {})
    arch    = artifacts.get("architect", {})
    em      = artifacts.get("engineering_manager", {})
    mkt     = artifacts.get("marketing", {})

    body = (
        _section_cover(startup_name, session_id, advisor, market)
        + _section_advisor(advisor)
        + _section_market(market)
        + _section_prd(prd)
        + _section_architect(arch)
        + _section_em(em)
        + _section_marketing(mkt)
        + '<div class="footer">Generated by Blueprint — AI Founder Orchestration System</div>'
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{_e(startup_name)} — Blueprint</title>
  <style>{_CSS}</style>
</head>
<body>{body}</body>
</html>"""


# ---------------------------------------------------------------------------
# PDF writer
# ---------------------------------------------------------------------------

def export_to_pdf(
    startup_name: str,
    session_id: str,
    artifacts: Dict[str, Any],
    output_dir: str = "exports",
) -> str:
    """
    Render the founder package to a PDF file and return the absolute path.

    Raises RuntimeError if xhtml2pdf reports a rendering failure.
    Cleans up the partial file on error so callers never see a corrupt PDF.
    """
    os.makedirs(output_dir, exist_ok=True)

    html_content = generate_report_html(startup_name, session_id, artifacts)
    pdf_path     = os.path.join(output_dir, f"{session_id}_report.pdf")

    with open(pdf_path, "w+b") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)

    if pisa_status.err:
        try:
            os.remove(pdf_path)
        except OSError:
            pass
        raise RuntimeError(
            f"xhtml2pdf rendering failed with error code {pisa_status.err}"
        )

    abs_path = os.path.abspath(pdf_path)
    logger.info("PDF report written to %s", abs_path)
    return abs_path

# ✅ P10: R1–R10 applied. [R3 relaxed: HTML string concatenation bounded by fixed artifact count]