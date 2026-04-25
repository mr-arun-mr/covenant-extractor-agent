"""
Generate a sample credit agreement PDF for testing the covenant extractor agent.

The PDF contains:
  - 6 pages of realistic credit agreement language
  - Red-colored text: amended/added provisions (detected via char non_stroking_color)
  - Strikethrough lines drawn over deleted/replaced text (detected via page.lines)
  - All five covenant types: financial, negative, affirmative, reporting, events of default

Run:
    python scripts/create_sample_pdf.py

Output:
    tests/fixtures/sample_credit_agreement.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas

OUTPUT = Path(__file__).parent.parent / "tests" / "fixtures" / "sample_credit_agreement.pdf"

W, H = letter          # 612 x 792 points
LEFT = inch            # left margin
FONT = "Helvetica"
BOLD = "Helvetica-Bold"
LINE_H = 14            # body line height (points)
MIN_Y = inch * 0.9     # bottom margin before page break


# ---------------------------------------------------------------------------
# Writer helper
# ---------------------------------------------------------------------------

class _Writer:
    """Thin wrapper around reportlab Canvas with convenience drawing methods."""

    def __init__(self, path: str | Path) -> None:
        self._c = rl_canvas.Canvas(str(path), pagesize=letter)
        self.y = H - inch

    # ── page control ────────────────────────────────────────────────────────

    def new_page(self) -> None:
        self._c.showPage()
        self.y = H - inch

    def _maybe_break(self, needed: float = LINE_H * 2) -> None:
        if self.y < MIN_Y + needed:
            self.new_page()

    def skip(self, pts: float = 6) -> None:
        self.y -= pts

    # ── text helpers ─────────────────────────────────────────────────────────

    def h1(self, text: str) -> None:
        self._maybe_break(50)
        self._c.setFont(BOLD, 14)
        self._c.drawString(LEFT, self.y, text)
        self.y -= 22

    def h2(self, text: str) -> None:
        self._maybe_break(36)
        self.skip(4)
        self._c.setFont(BOLD, 11)
        self._c.drawString(LEFT, self.y, text)
        self.y -= 17

    def p(self, text: str, indent: float = 0) -> None:
        self._maybe_break()
        self._c.setFont(FONT, 10)
        self._c.drawString(LEFT + indent, self.y, text)
        self.y -= LINE_H

    def red(self, text: str, indent: float = 0) -> None:
        """Draw an entire line in red (new / added language)."""
        self._maybe_break()
        self._c.setFont(FONT, 10)
        self._c.setFillColorRGB(1, 0, 0)
        self._c.drawString(LEFT + indent, self.y, text)
        self._c.setFillColorRGB(0, 0, 0)
        self.y -= LINE_H

    def amended(
        self,
        prefix: str,
        old: str,
        new: str,
        suffix: str = "",
        indent: float = 0,
    ) -> None:
        """
        Draw one line: [prefix] [old — strikethrough] [new — red] [suffix].

        The strikethrough is a thin horizontal line drawn mid-height over `old`.
        pdfplumber sees it as a content-stream line object (page.lines) whose
        vertical midpoint overlaps the text characters.
        """
        self._maybe_break()
        c = self._c
        x = LEFT + indent
        y = self.y

        c.setFont(FONT, 10)

        if prefix:
            c.drawString(x, y, prefix)
            x += c.stringWidth(prefix, FONT, 10)

        # Old text with strikethrough line drawn at ≈ mid-height of 10 pt text
        if old:
            c.drawString(x, y, old)
            w = c.stringWidth(old, FONT, 10)
            strike_y = y + 3.5          # 3.5 pt above baseline ≈ x-height centre
            c.setLineWidth(0.75)
            c.setStrokeColorRGB(0, 0, 0)
            c.line(x, strike_y, x + w, strike_y)
            x += w + 3

        # New text in red
        if new:
            c.setFillColorRGB(1, 0, 0)
            c.drawString(x, y, new)
            c.setFillColorRGB(0, 0, 0)
            x += c.stringWidth(new, FONT, 10) + 2

        if suffix:
            c.drawString(x, y, suffix)

        self.y -= LINE_H

    def footer(self, text: str) -> None:
        self._c.setFont(FONT, 8)
        self._c.setFillColorRGB(0.5, 0.5, 0.5)
        self._c.drawCentredString(W / 2, inch * 0.6, text)
        self._c.setFillColorRGB(0, 0, 0)

    def save(self) -> None:
        self._c.save()


# ---------------------------------------------------------------------------
# Document content
# ---------------------------------------------------------------------------

def build(output: str | Path = OUTPUT) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    w = _Writer(output)
    c = w._c                # direct canvas access for centred strings

    _SAMPLE_NOTE = "SAMPLE DOCUMENT — FOR TESTING PURPOSES ONLY"

    # ── PAGE 1: Cover ────────────────────────────────────────────────────────
    w.skip(60)
    c.setFont(BOLD, 22)
    c.drawCentredString(W / 2, w.y, "CREDIT AGREEMENT")
    w.y -= 36

    c.setFont(FONT, 12)
    c.drawCentredString(W / 2, w.y, "Dated as of March 15, 2024")
    w.y -= 48

    w.p("BORROWER:              TechCorp International, Inc., a Delaware corporation")
    w.p("GUARANTORS:            TechCorp Holdings LLC; TechCorp Operating LLC")
    w.p("ADMINISTRATIVE AGENT:  First National Bank, N.A.")
    w.p("LENDERS:               The several lenders from time to time party hereto")
    w.skip(24)
    w.p("AGGREGATE COMMITMENTS: $200,000,000")
    w.p("FACILITY TYPE:         Senior Secured Revolving Credit Facility")
    w.p("CLOSING DATE:          March 15, 2024")
    w.p("MATURITY DATE:         March 15, 2029")
    w.skip(32)

    c.setFont(BOLD, 10)
    c.drawCentredString(W / 2, w.y,
                        "As amended by Amendment No. 1 dated January 10, 2025")
    w.y -= 16
    c.setFont(FONT, 9)
    c.drawCentredString(W / 2, w.y,
                        "Amended provisions are shown in red.  "
                        "Deleted provisions are shown in strikethrough.")
    w.footer(_SAMPLE_NOTE)

    # ── PAGE 2: Table of Contents ─────────────────────────────────────────────
    w.new_page()
    w.h1("TABLE OF CONTENTS")

    toc = [
        ("Article I",    "Definitions and Interpretation", 3),
        ("Article II",   "The Credit Facility", 4),
        ("Article III",  "Conditions Precedent", 5),
        ("Article IV",   "Representations and Warranties", 6),
        ("Article V",    "Conditions to Each Extension of Credit", 7),
        ("Article VI",   "Financial Covenants", 8),
        ("Article VII",  "Negative Covenants", 10),
        ("Article VIII", "Affirmative Covenants", 13),
        ("Article IX",   "Reporting Covenants", 15),
        ("Article X",    "Events of Default", 17),
        ("Article XI",   "Miscellaneous", 19),
    ]
    for art, title, pg in toc:
        c.setFont(FONT, 10)
        c.drawString(LEFT, w.y, f"{art:<16}{title}")
        c.drawRightString(W - inch, w.y, str(pg))
        w.y -= LINE_H

    w.footer(_SAMPLE_NOTE)

    # ── PAGE 3: Article VI — Financial Covenants ──────────────────────────────
    w.new_page()
    w.h1("ARTICLE VI — FINANCIAL COVENANTS")

    w.h2("Section 6.01  Maximum Leverage Ratio")
    w.p("The Borrower shall not permit the Leverage Ratio, as of the last day of any")
    w.p("fiscal quarter ending on or after March 31, 2024, to be greater than")
    w.amended("    ", "4.00", "4.50", " to 1.00.")
    w.p("Test frequency:   Quarterly (as of the last day of each fiscal quarter)")
    w.p("Schedule start:   March 31, 2024")
    w.p("Maturity date:    March 15, 2029")
    w.p("Grace period:     None — tested as of the applicable quarter-end date")
    w.skip(10)

    w.h2("Section 6.02  Minimum Interest Coverage Ratio")
    w.p("The Borrower shall maintain the Interest Coverage Ratio of not less than")
    w.amended("    ", "2.25", "2.50", " to 1.00, measured on a trailing twelve-month basis.")
    w.p("Test frequency:   Quarterly (each fiscal quarter end)")
    w.p("Schedule start:   March 31, 2024")
    w.p("Maturity date:    March 15, 2029")
    w.p("Grace period:     30 days following written notice from Administrative Agent")
    w.skip(10)

    w.h2("Section 6.03  Minimum Liquidity")
    w.p("The Borrower shall maintain, at all times, unrestricted cash and Cash Equivalents")
    w.p("of not less than $25,000,000 (twenty-five million U.S. dollars).")
    w.p("Test frequency:   Continuous; confirmed monthly as of the last Business Day")
    w.p("Schedule start:   Closing Date (March 15, 2024)")
    w.p("Maturity date:    March 15, 2029")
    w.p("Grace period:     5 Business Days")
    w.skip(10)

    w.h2("Section 6.04  Maximum Capital Expenditures")
    w.p("The Borrower shall not permit Capital Expenditures in any fiscal year to exceed")
    w.amended("    ", "$30,000,000", "$40,000,000", " in the aggregate.")
    w.p("Test frequency:   Annually (fiscal year end, December 31)")
    w.p("Schedule start:   Fiscal year ending December 31, 2024")
    w.p("Maturity date:    March 15, 2029")
    w.p("Grace period:     None")

    w.footer(_SAMPLE_NOTE)

    # ── PAGE 4: Article VII — Negative Covenants ──────────────────────────────
    w.new_page()
    w.h1("ARTICLE VII — NEGATIVE COVENANTS")

    w.h2("Section 7.01  Indebtedness")
    w.p("The Borrower shall not, and shall not permit any Restricted Subsidiary to, create,")
    w.p("incur, assume or otherwise become liable for any Indebtedness, except:")
    w.skip(4)
    w.p("(a) Indebtedness under this Agreement and the other Loan Documents;", indent=20)
    w.p("(b) Existing Indebtedness listed on Schedule 7.01 as of the Closing Date;", indent=20)
    w.p("(c) purchase money Indebtedness and Capital Lease Obligations not to exceed,", indent=20)
    w.amended("    in the aggregate at any time, ", "$10,000,000", "$15,000,000", ".", indent=20)
    w.p("(d) unsecured intercompany Indebtedness among the Borrower and its Subsidiaries.", indent=20)
    w.skip(10)

    w.h2("Section 7.02  Liens")
    w.p("The Borrower shall not create, incur, assume or permit any Lien upon any of its")
    w.p("property or assets, whether now owned or hereafter acquired, except Permitted Liens.")
    w.skip(10)

    w.h2("Section 7.03  Restricted Payments")
    w.p("The Borrower shall not declare or pay any cash dividend or distribution, except:")
    w.skip(4)
    w.p("(a) dividends payable solely in Equity Interests of the Borrower;", indent=20)
    w.p("(b) cash dividends not to exceed, in any fiscal year,", indent=20)
    w.amended("    ", "$5,000,000", "$8,000,000", ",", indent=20)
    w.p("    provided no Default or Event of Default exists at the time of payment;", indent=20)
    w.p("(c) repurchases of Equity Interests from departing employees,", indent=20)
    w.amended("    not to exceed ", "$2,000,000", "$3,000,000", " per fiscal year.", indent=20)
    w.skip(10)

    w.h2("Section 7.04  Mergers and Acquisitions")
    w.p("The Borrower shall not merge with or into, or acquire any Person, unless:")
    w.p("(a) the Borrower is the surviving or resulting entity;", indent=20)
    w.p("(b) no Default or Event of Default has occurred and is continuing;", indent=20)
    w.p("(c) aggregate consideration does not exceed $50,000,000 in any fiscal year.", indent=20)
    w.skip(10)

    w.h2("Section 7.05  Asset Dispositions")
    w.p("The Borrower shall not sell, transfer, lease or otherwise dispose of assets except:")
    w.p("(a) dispositions of obsolete equipment in the ordinary course of business;", indent=20)
    w.p("(b) sales of inventory in the ordinary course of business;", indent=20)
    w.amended(
        "(c) other asset sales not to exceed ",
        "$20,000,000", "$30,000,000",
        " in the aggregate per fiscal year.", indent=20,
    )

    w.footer(_SAMPLE_NOTE)

    # ── PAGE 5: Articles VIII & IX ────────────────────────────────────────────
    w.new_page()
    w.h1("ARTICLE VIII — AFFIRMATIVE COVENANTS")

    w.h2("Section 8.01  Insurance")
    w.p("The Borrower shall maintain, with financially sound and reputable companies,")
    w.p("insurance with respect to its properties and business in such amounts as are")
    w.p("customarily maintained by Persons engaged in the same or similar business.")
    w.skip(4)
    w.red("    Amendment No. 1 addition: The Borrower shall also maintain cyber liability")
    w.red("    insurance with limits of no less than $10,000,000 per occurrence.")
    w.skip(10)

    w.h2("Section 8.02  Payment of Taxes")
    w.p("The Borrower shall pay and discharge all material taxes, assessments and")
    w.p("governmental charges before they become delinquent, subject to the right to")
    w.p("contest such items in good faith by appropriate proceedings.")
    w.skip(10)

    w.h2("Section 8.03  Maintenance of Properties")
    w.p("The Borrower shall maintain and preserve all material properties in good")
    w.p("working order and condition, ordinary wear and tear excepted.")
    w.skip(10)

    w.h2("Section 8.04  Compliance with Laws")
    w.p("The Borrower shall comply in all material respects with all applicable laws,")
    w.p("regulations, orders and requirements of any Governmental Authority.")
    w.skip(16)

    w.h1("ARTICLE IX — REPORTING COVENANTS")

    w.h2("Section 9.01  Financial Statements")
    w.p("The Borrower shall deliver to the Administrative Agent:")
    w.skip(4)
    w.p("(a) Quarterly: within 45 days after each of the first three fiscal quarters,", indent=20)
    w.p("    unaudited consolidated financial statements prepared in accordance with GAAP;", indent=20)
    w.p("(b) Annual: within 90 days after each fiscal year end, audited consolidated", indent=20)
    w.p("    financial statements certified by independent registered public accountants;", indent=20)
    w.p("(c) Management Discussion and Analysis accompanying each set of financials.", indent=20)
    w.skip(10)

    w.h2("Section 9.02  Compliance Certificate")
    w.p("Together with the financial statements required under Section 9.01(a) and (b),")
    w.p("a Compliance Certificate signed by a Responsible Officer demonstrating compliance")
    w.p("with each Financial Covenant in Article VI and setting out the applicable ratios.")
    w.skip(10)

    w.h2("Section 9.03  Notices")
    w.p("Promptly upon obtaining knowledge, notify the Administrative Agent of:")
    w.p("(a) any Event of Default or Potential Default;", indent=20)
    w.p("(b) any pending or threatened litigation with potential liability over $5,000,000;", indent=20)
    w.p("(c) any Material Adverse Change.", indent=20)

    w.footer(_SAMPLE_NOTE)

    # ── PAGE 6: Article X — Events of Default ────────────────────────────────
    w.new_page()
    w.h1("ARTICLE X — EVENTS OF DEFAULT")

    w.h2("Section 10.01  Events of Default")
    w.p("Each of the following shall constitute an Event of Default:")
    w.skip(4)

    w.p("(a) Payment Default: failure to pay any principal when due; or failure to pay", indent=20)
    w.p("    interest, fees or other amounts within 5 Business Days of the due date;", indent=20)
    w.skip(4)

    w.p("(b) Representation Default: any representation or warranty made herein proves", indent=20)
    w.p("    false or misleading in any material respect when made or deemed made;", indent=20)
    w.skip(4)

    w.p("(c) Financial Covenant Default: failure to comply with any covenant in Article VI;", indent=20)
    w.p("    no cure period applies to Financial Covenant defaults;", indent=20)
    w.skip(4)

    w.p("(d) Other Covenant Default: failure to comply with any other covenant or", indent=20)
    w.p("    obligation within 30 days after written notice from Administrative Agent;", indent=20)
    w.skip(4)

    w.p("(e) Cross-Default: default under any other Indebtedness in excess of $10,000,000;", indent=20)
    w.skip(4)

    w.p("(f) Insolvency: commencement of bankruptcy, insolvency, or similar proceedings", indent=20)
    w.p("    and, if involuntary, not dismissed within 60 days of filing;", indent=20)
    w.skip(4)

    w.p("(g) Judgment Default: entry of judgments in excess of $10,000,000 in aggregate,", indent=20)
    w.p("    not stayed or discharged within 30 days;", indent=20)
    w.skip(4)

    w.p("(h) Change of Control: any Person acquires beneficial ownership of more than 50%", indent=20)
    w.p("    of the voting Equity Interests of the Borrower.", indent=20)
    w.skip(16)

    w.h2("Section 10.02  Remedies")
    w.p("Upon the occurrence and continuation of an Event of Default, the Administrative")
    w.p("Agent may, upon the instruction of the Required Lenders, declare all Loans")
    w.p("immediately due and payable and exercise all other rights and remedies available")
    w.p("under this Agreement and applicable law.")
    w.skip(16)

    c.setFont(FONT, 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(W / 2, w.y, "[Signature pages follow]")
    c.setFillColorRGB(0, 0, 0)

    w.footer(_SAMPLE_NOTE)
    w.save()
    print(f"Generated: {output}")


if __name__ == "__main__":
    build()
