"""
Weekly digest — HTML summary of new Tier 1 / Tier 2 targets.

generate() builds an HTML report of companies added in the last N days and
writes it to config.DIGEST_OUTPUT_PATH (weekly_digest.html), overwriting the
prior file. send() additionally emails it to WEEKLY_DIGEST_RECIPIENTS, but
only if SMTP is configured; otherwise it logs and writes the file only.
"""

import html
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    DIGEST_OUTPUT_PATH,
    FIRM_NAME,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    WEEKLY_DIGEST_RECIPIENTS,
)
from database.db import Database

_NAVY = "#1B365D"
_GOLD = "#D4A843"


def _esc(value):
    return html.escape("" if value is None else str(value))


def _fmt_money(value):
    if value in (None, ""):
        return ""
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return _esc(value)


class DigestGenerator:
    def __init__(self, db=None):
        self.db = db or Database()

    def generate(self, days=7):
        since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
        tier1 = [r for r in self.db.get_recent(since, tiers=(1,))]
        tier2 = [r for r in self.db.get_recent(since, tiers=(2,))]

        html_doc = self._render(tier1, tier2, days)
        DIGEST_OUTPUT_PATH.write_text(html_doc, encoding="utf-8")
        logging.info(
            "Digest generated: %s (%d T1, %d T2)",
            DIGEST_OUTPUT_PATH,
            len(tier1),
            len(tier2),
        )
        return html_doc

    def _render(self, tier1, tier2, days):
        today = datetime.now().strftime("%B %d, %Y")
        parts = [
            "<html><body style=\"font-family:Calibri,Arial,sans-serif;color:#222;\">",
            f"<h1 style=\"color:{_NAVY};\">{_esc(FIRM_NAME)} — Deal Pipeline Digest</h1>",
            f"<p style=\"color:#666;\">{today} &middot; new targets in the last "
            f"{days} days</p>",
            self._section("Tier 1 — Priority", tier1, _GOLD),
            self._section("Tier 2 — Watch List", tier2, _NAVY),
            "<p style=\"color:#999;font-size:11px;margin-top:30px;\">Revenue and "
            "ownership figures are proxies/estimates, not verified financials. "
            "This pipeline finds matching companies; it does not confirm they are "
            "for sale.</p>",
            "</body></html>",
        ]
        return "\n".join(parts)

    def _section(self, title, rows, accent):
        if not rows:
            return (
                f"<h2 style=\"color:{accent};\">{_esc(title)}</h2>"
                "<p style=\"color:#888;\">No new targets this period.</p>"
            )
        header = (
            f"<h2 style=\"color:{accent};\">{_esc(title)} ({len(rows)})</h2>"
            "<table cellpadding=\"6\" cellspacing=\"0\" border=\"0\" "
            "style=\"border-collapse:collapse;width:100%;font-size:13px;\">"
            "<tr style=\"background:#f1f4f7;text-align:left;\">"
            "<th>Score</th><th>Company</th><th>State</th><th>Sector</th>"
            "<th>Rev Est</th><th>Source</th><th>Signals</th></tr>"
        )
        body = []
        for r in rows:
            rev = ""
            if r.get("revenue_estimate_low") or r.get("revenue_estimate_high"):
                rev = (
                    f"{_fmt_money(r.get('revenue_estimate_low'))}–"
                    f"{_fmt_money(r.get('revenue_estimate_high'))}"
                )
            elif r.get("listed_revenue"):
                rev = _fmt_money(r.get("listed_revenue"))
            signals = []
            if r.get("osha_severity") and r["osha_severity"] != "none":
                signals.append(f"OSHA: {r['osha_severity']}")
            if r.get("filing_status") == "lapsed":
                signals.append("lapsed reg")
            if r.get("days_on_market"):
                signals.append(f"{r['days_on_market']}d on market")
            link = r.get("listing_url")
            company = _esc(r.get("company_name"))
            if link:
                company = f"<a href=\"{_esc(link)}\">{company}</a>"
            body.append(
                "<tr style=\"border-bottom:1px solid #e0e0e0;\">"
                f"<td><b>{_esc(r.get('score_total'))}</b></td>"
                f"<td>{company}</td>"
                f"<td>{_esc(r.get('state'))}</td>"
                f"<td>{_esc(r.get('trs_sector'))}</td>"
                f"<td>{rev}</td>"
                f"<td>{_esc(r.get('source'))}</td>"
                f"<td>{_esc(', '.join(signals))}</td>"
                "</tr>"
            )
        return header + "".join(body) + "</table>"

    def send(self, days=7):
        html_doc = self.generate(days=days)
        if not SMTP_HOST:
            logging.info("SMTP not configured; digest written to file only.")
            print("  Digest written (email skipped — SMTP not configured).")
            return False
        if not WEEKLY_DIGEST_RECIPIENTS:
            logging.info("No digest recipients configured; skipping send.")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{FIRM_NAME} — Weekly Deal Pipeline Digest"
        msg["From"] = SMTP_FROM
        msg["To"] = ", ".join(WEEKLY_DIGEST_RECIPIENTS)
        msg.attach(MIMEText(html_doc, "html"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, WEEKLY_DIGEST_RECIPIENTS, msg.as_string())
            logging.info("Digest emailed to %s", WEEKLY_DIGEST_RECIPIENTS)
            print(f"  Digest emailed to {len(WEEKLY_DIGEST_RECIPIENTS)} recipient(s).")
            return True
        except Exception as e:  # noqa: BLE001
            logging.error("Digest email failed: %s", e)
            print(f"  Digest email failed: {e}")
            return False
