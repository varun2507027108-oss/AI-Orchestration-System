import os
import logging
import html
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

from xhtml2pdf import pisa

def clean_and_wrap(text: str, max_len: int = 40, is_pre: bool = False) -> str:
    """
    Escapes text for HTML safety and wraps any word longer than max_len.
    Uses \n for line breaks if is_pre is True, otherwise <br/>.
    """
    if not text:
        return ""
    
    # First escape for HTML safety
    escaped_text = html.escape(str(text))
    
    words = []
    # Split by whitespace while keeping whitespace transitions
    parts = re.split(r"(\s+)", escaped_text)
    for part in parts:
        if not part or part.isspace():
            words.append(part)
        else:
            if len(part) > max_len:
                # Insert break character every max_len characters inside the word
                break_char = "\n" if is_pre else "<br/>"
                subparts = [part[i:i+max_len] for i in range(0, len(part), max_len)]
                words.append(break_char.join(subparts))
            else:
                words.append(part)
    return "".join(words)

def generate_report_html(startup_name: str, session_id: str, artifacts: Dict[str, Any]) -> str:
    """
    Compile all session artifacts into a beautifully styled HTML template.
    """
    advisor = artifacts.get("startup_advisor", {})
    market = artifacts.get("market_research", {})
    prd = artifacts.get("product_manager", {})
    arch = artifacts.get("architect", {})
    em = artifacts.get("engineering_manager", {})
    mkt = artifacts.get("marketing", {})
    
    # Advisor Risk CSS styling
    risk_score = advisor.get("risk_score", 0.0)
    risk_class = "risk-low" if risk_score <= 0.4 else ("risk-high" if risk_score > 0.6 else "callout")
    
    # Wrap base metadata
    startup_name_wrapped = clean_and_wrap(startup_name, 40)
    session_id_wrapped = clean_and_wrap(session_id, 40)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{startup_name_wrapped} - AI Founder Launch Report</title>
    <style>
        body {{
            font-family: Helvetica, Arial, sans-serif;
            color: #1a202c;
            line-height: 1.6;
            margin: 40px;
            padding: 0;
            background-color: #ffffff;
        }}
        h1 {{
            font-size: 28px;
            font-weight: 700;
            color: #0f172a;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
            margin-bottom: 10px;
        }}
        .meta-subtitle {{
            font-size: 14px;
            color: #64748b;
            margin-bottom: 40px;
        }}
        h2 {{
            font-size: 20px;
            font-weight: 600;
            color: #1e293b;
            margin-top: 40px;
            margin-bottom: 15px;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 5px;
        }}
        h3 {{
            font-size: 16px;
            font-weight: 600;
            color: #334155;
            margin-top: 25px;
            margin-bottom: 10px;
        }}
        p {{
            margin: 0 0 15px 0;
            font-size: 14px;
        }}
        .callout {{
            background-color: #f8fafc;
            border-left: 4px solid #3b82f6;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
            font-size: 14px;
        }}
        .risk-high {{
            border-left: 4px solid #ef4444;
            background-color: #fef2f2;
        }}
        .risk-low {{
            border-left: 4px solid #10b981;
            background-color: #ecfdf5;
        }}
        ul {{
            margin: 0 0 20px 20px;
            padding: 0;
            font-size: 14px;
        }}
        li {{
            margin-bottom: 5px;
        }}
        code, pre {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
        }}
        pre {{
            display: block;
            padding: 15px;
            margin-bottom: 20px;
            overflow-x: auto;
            white-space: pre-wrap;
        }}
        .footer {{
            margin-top: 60px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
        }}
        .page-break {{
            page-break-before: always;
        }}
    </style>
</head>
<body>
    <h1>{startup_name_wrapped}</h1>
    <div class="meta-subtitle">AI Founder OS Orchestration Report | Session: {session_id_wrapped}</div>

    <!-- 1. Startup Advisor -->
    <h2>1. Startup Advisor Validation</h2>
    <div class="callout {risk_class}">
        <strong>Verdict:</strong> {clean_and_wrap(advisor.get("verdict", "N/A"), 40)}<br/>
        <strong>Risk Score:</strong> {risk_score}
    </div>
    <p><strong>Reasoning:</strong> {clean_and_wrap(advisor.get("reasoning", "N/A"), 80)}</p>
    """
    
    if advisor.get("red_flags"):
        html_content += "<h3>Red Flags Flagged</h3><ul>"
        for rf in advisor.get("red_flags", []):
            html_content += f"<li>{clean_and_wrap(rf, 60)}</li>"
        html_content += "</ul>"

    # 2. Market Research
    html_content += f"""
    <div class="page-break"></div>
    <h2>2. Market Research</h2>
    <p><strong>TAM Estimate:</strong> {clean_and_wrap(market.get("tam_estimate", "N/A"), 40)}</p>
    """
    
    if market.get("competitors"):
        html_content += "<h3>Key Competitors</h3><ul>"
        for comp in market.get("competitors", []):
            comp_name = clean_and_wrap(comp.get('name', ''), 40)
            comp_desc = clean_and_wrap(comp.get('description', ''), 80)
            comp_url_raw = comp.get('url', '')
            comp_url_escaped = html.escape(comp_url_raw) if comp_url_raw else "#"
            comp_url_wrapped = clean_and_wrap(comp_url_raw, 40)
            html_content += f"<li><strong>{comp_name}</strong>: {comp_desc} (<a href='{comp_url_escaped}'>{comp_url_wrapped}</a>)</li>"
        html_content += "</ul>"
        
    if market.get("trends"):
        html_content += "<h3>Key Market Trends</h3><ul>"
        for trend in market.get("trends", []):
            html_content += f"<li>{clean_and_wrap(trend, 80)}</li>"
        html_content += "</ul>"

    if market.get("sources"):
        html_content += "<h3>Sources Cited</h3><ul>"
        for src in market.get("sources", []):
            src_escaped = html.escape(src)
            src_wrapped = clean_and_wrap(src, 40)
            html_content += f"<li><a href='{src_escaped}'>{src_wrapped}</a></li>"
        html_content += "</ul>"

    # 3. Product Manager
    html_content += f"""
    <div class="page-break"></div>
    <h2>3. Product Requirement Document (PRD)</h2>
    <p><strong>Problem Statement:</strong></p>
    <p>{clean_and_wrap(prd.get("problem_statement", "N/A"), 80)}</p>
    """
    
    if prd.get("user_stories"):
        html_content += "<h3>User Stories</h3><ul>"
        for story in prd.get("user_stories", []):
            html_content += f"<li>{clean_and_wrap(story, 80)}</li>"
        html_content += "</ul>"
        
    if prd.get("features"):
        html_content += "<h3>Core Features & Priority</h3><ul>"
        for feat in prd.get("features", []):
            feat_priority = clean_and_wrap(feat.get('priority', 'Medium'), 40)
            feat_name = clean_and_wrap(feat.get('name', ''), 40)
            feat_desc = clean_and_wrap(feat.get('description', ''), 80)
            html_content += f"<li><strong>[{feat_priority}] {feat_name}</strong>: {feat_desc}</li>"
        html_content += "</ul>"

    if prd.get("roadmap_phases"):
        html_content += "<h3>Roadmap Phases</h3><ul>"
        for phase in prd.get("roadmap_phases", []):
            phase_name = clean_and_wrap(phase.get('name', ''), 40)
            items_str = ", ".join(phase.get("items", []))
            items_wrapped = clean_and_wrap(items_str, 60)
            html_content += f"<li><strong>{phase_name}</strong>: {items_wrapped}</li>"
        html_content += "</ul>"

    # 4. Architect
    html_content += f"""
    <div class="page-break"></div>
    <h2>4. System Architecture Specification</h2>
    <p><strong>System Design Notes:</strong></p>
    <p>{clean_and_wrap(arch.get("system_design_notes", "N/A"), 80)}</p>
    """
    
    if arch.get("db_schema_sql"):
        html_content += f"<h3>Database Schema (SQL)</h3><pre><code>{clean_and_wrap(arch.get('db_schema_sql', ''), 60, is_pre=True)}</code></pre>"
        
    if arch.get("db_schema_mermaid"):
        html_content += f"<h3>Architecture Diagram (Mermaid)</h3><pre><code>{clean_and_wrap(arch.get('db_schema_mermaid', ''), 60, is_pre=True)}</code></pre>"
        
    if arch.get("api_endpoints"):
        html_content += "<h3>API Endpoints Contract</h3><ul>"
        for ep in arch.get("api_endpoints", []):
            ep_method = clean_and_wrap(ep.get('method', 'GET'), 10)
            ep_path = clean_and_wrap(ep.get('path', ''), 40)
            ep_desc = clean_and_wrap(ep.get('description', ''), 80)
            html_content += f"<li><code>{ep_method} {ep_path}</code> - {ep_desc}</li>"
        html_content += "</ul>"

    # 5. Engineering Manager
    html_content += f"""
    <div class="page-break"></div>
    <h2>5. Sprints and Issues Plan</h2>
    """
    
    if em.get("sprints"):
        html_content += "<h3>Sprint Roadmap</h3><ul>"
        for sp in em.get("sprints", []):
            sp_name = clean_and_wrap(sp.get('name', ''), 40)
            issues_str = ", ".join(sp.get("issue_titles", []))
            issues_wrapped = clean_and_wrap(issues_str, 60)
            html_content += f"<li><strong>{sp_name}</strong>: {issues_wrapped}</li>"
        html_content += "</ul>"
        
    if em.get("issues"):
        html_content += "<h3>GitHub Issues Backlog</h3><ul>"
        for issue in em.get("issues", []):
            issue_title = clean_and_wrap(issue.get('title', ''), 60)
            labels_str = ", ".join(issue.get("labels", []))
            labels_wrapped = clean_and_wrap(labels_str, 40)
            issue_body = clean_and_wrap(issue.get('body', ''), 80)
            html_content += f"<li><strong>{issue_title}</strong> (Labels: <code>{labels_wrapped}</code>)<br/>{issue_body}</li>"
        html_content += "</ul>"

    # 6. Marketing
    html_content += f"""
    <div class="page-break"></div>
    <h2>6. Marketing Launch Assets</h2>
    <h3>Landing Page Copy</h3>
    <p>{clean_and_wrap(mkt.get("landing_copy", "N/A"), 80)}</p>
    
    <h3>LinkedIn Launch Post</h3>
    <p style="white-space: pre-wrap;">{clean_and_wrap(mkt.get("linkedin_post", "N/A"), 80, is_pre=True)}</p>
    
    <h3>Email Campaign Copy</h3>
    <p style="white-space: pre-wrap;">{clean_and_wrap(mkt.get("email_campaign", "N/A"), 80, is_pre=True)}</p>
    """

    html_content += """
    <div class="footer">
        Generated by AI Founder Orchestration System. All Rights Reserved.
    </div>
</body>
</html>
"""
    return html_content

def export_to_pdf(startup_name: str, session_id: str, artifacts: Dict[str, Any], output_dir: str = "exports") -> str:
    """
    Compiles all stage artifacts for a session and renders them to a PDF file using xhtml2pdf.
    Returns the absolute path to the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    html_content = generate_report_html(startup_name, session_id, artifacts)
    pdf_path = os.path.join(output_dir, f"{session_id}_report.pdf")
    
    with open(pdf_path, "w+b") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
        
    if pisa_status.err:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass
        raise RuntimeError(f"xhtml2pdf rendering failed with status code {pisa_status.err}")
        
    logger.info(f"Generated PDF report successfully using xhtml2pdf: {pdf_path}")
    return os.path.abspath(pdf_path)
