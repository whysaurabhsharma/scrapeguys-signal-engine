"""Build a two-tab xlsx (ICP and Targeting, Accounts) from data/scored.csv. Stdlib only. Read-only on the CSV."""
import csv
import sys
import zipfile
from xml.sax.saxutils import escape

SRC = sys.argv[1]
OUT = sys.argv[2]

ICP_ORDER = {"ai": 0, "travel": 1, "commerce": 2}
rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
rows.sort(key=lambda r: (ICP_ORDER[r["icp"]], -float(r["score"])))
N = len(rows)
LAST = N + 1  # last data row on Accounts

# styles: 0 normal, 1 header, 2 title, 3 wrap, 4 section, 5 number 0.0, 6 note wrap, 7 bold
def col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s

def cell(ref, v, style=0):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'
    if isinstance(v, str) and v.startswith("="):
        return f'<c r="{ref}" s="{style}"><f>{escape(v[1:])}</f></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>'

def sheet_xml(grid, widths, freeze=None, merges=(), autofilter=None):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if freeze:
        out.append(f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{freeze}" topLeftCell="A{freeze+1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    out.append("<cols>" + "".join(
        f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)) + "</cols>")
    out.append("<sheetData>")
    for r, row in enumerate(grid, start=1):
        if row is None:
            continue
        cells = "".join(cell(f"{col(c)}{r}", v, s) for c, (v, s) in enumerate(row) if v is not None)
        out.append(f'<row r="{r}">{cells}</row>')
    out.append("</sheetData>")
    if autofilter:
        out.append(f'<autoFilter ref="{autofilter}"/>')
    if merges:
        out.append(f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges) + "</mergeCells>")
    out.append("</worksheet>")
    return "".join(out)

def R(*cells):
    """cells as (value, style) tuples, or plain values (text gets wrap style 3, numbers style 0)."""
    res = []
    for c in cells:
        if isinstance(c, tuple):
            res.append(c)
        elif isinstance(c, str) and not c.startswith("="):
            res.append((c, 3))
        else:
            res.append((c, 0))
    return res

# ---------- Tab 1: ICP and Targeting ----------
t = {}
t[1] = [("Who we sell to and how we find them", 2)]
t[2] = [("We sell live web data to companies that cannot see a market that changes hourly. The system finds public, dated evidence of that need, scores it with fixed rules, and writes a sourced brief. It drafts. A human sends.", 6)]
t[4] = [("Our three ICPs", 4)]
hdr = ["ICP", "Who they are", "What they cannot see", "Market", "Accounts", "Tier A", "Tier B", "Nurture", "Reject"]
t[5] = [(h, 1) for h in hdr]
icps = [
    ("ai", "AI products that answer users from the live web: shopping, travel and research assistants.",
     "A live view of the web their product answers from. Prices and availability go stale between crawls, so the user is shown something no longer true.", "Global"),
    ("travel", "Hotels, rentals and travel brands sold through online travel agencies (OTAs).",
     "Their own rates across the OTAs reselling them. Parity leaks and undercutting go unseen until revenue has moved.", "Global"),
    ("commerce", "Consumer brands selling on quick-commerce apps and marketplaces.",
     "Their SKUs and competitors across quick-commerce and marketplaces, where price, stock and placement change hourly.",
     "Global. India (Blinkit, Zepto, Instamart) preferred on equal evidence."),
]
for i, (k, who, gap, mkt) in enumerate(icps):
    r = 6 + i
    t[r] = R((k, 7), who, gap, mkt,
             f'=COUNTIF(Accounts!$A$2:$A${LAST},$A{r})',
             f'=COUNTIFS(Accounts!$A$2:$A${LAST},$A{r},Accounts!$E$2:$E${LAST},"A")',
             f'=COUNTIFS(Accounts!$A$2:$A${LAST},$A{r},Accounts!$E$2:$E${LAST},"B")',
             f'=COUNTIFS(Accounts!$A$2:$A${LAST},$A{r},Accounts!$E$2:$E${LAST},"nurture")',
             f'=COUNTIFS(Accounts!$A$2:$A${LAST},$A{r},Accounts!$E$2:$E${LAST},"reject")')
t[9] = R(("Total", 7), None, None, None, *[(f"=SUM({col(c)}6:{col(c)}8)", 7) for c in range(4, 9)])

t[11] = [("Who we do not target", 4)]
t[12] = [("Excluded", 1), ("Why", 1)]
t[13] = R(("Scraping, proxy and extraction vendors", 7), "They hire scraping engineers because scraping is their product, not their problem.")
t[14] = R(("Frontier AI labs and hyperscalers", 7), "They run web-scale crawling as core infrastructure (OpenAI, ElevenLabs and similar). Having engineers is not a reason to exclude anyone else.")
t[15] = R(("Suppression list", 7), "Any domain in config/suppress.csv is rejected at ingest.")

t[17] = [("How we target", 4)]
t[18] = [("Step", 1), ("What happens", 1), ("Rule", 1)]
steps = [
    ("1. Discover", "Search ATS job boards for scraping and data roles, check likely companies' job boards directly, and read quick-commerce vendor case studies and founder interviews where a brand describes its own problem.",
     "Public sources only. Generic funding search was dropped: it returned AI mega-rounds and no buyers."),
    ("2. Confirm a dated signal", "Each account needs a hiring, funding, launch or complaint signal with the date the event happened.",
     "No date, no signal. No claim without a URL."),
    ("3. Disqualify", "Remove vendors, frontier labs, hyperscalers and suppressed domains.", "Narrow exclusions only."),
    ("4. Stage and ingest", "Research is written as JSON and loaded by scripts/ingest.py, which assigns ids and rejects bad rows.",
     "Scripts write the data files. Nothing is edited by hand."),
    ("5. Score", "Score = ICP match (max 30) + pain (max 40) + capacity (max 15) + reachability (max 15). Pain decays with each signal's age.",
     "Scored by scripts/score.py. Never by hand."),
    ("6. Tier", "Accounts are tiered by score plus the gates below.", "Thresholds fixed before any row was scored."),
    ("7. Brief and asset", "Each Tier A account gets a sourced first-touch brief and an ICP-specific data asset.",
     "Every draft is marked DRAFT - NOT SENT."),
]
for i, s in enumerate(steps):
    t[19 + i] = R((s[0], 7), s[1], s[2])

t[27] = [("Signals and how they are weighted", 4)]
t[28] = [(h, 1) for h in ["Signal", "Pain points at day 0", "Half-life (days)", "Where the date comes from"]]
sig = [
    ("hiring", 18, 60, "Public ATS JSON API, never the HTML page. Greenhouse first_published preferred; Ashby publishedAt is a ceiling."),
    ("funding", 16, 120, "Announcement date. The most reliable trigger."),
    ("launch", 14, 90, "Press or product announcement date."),
    ("complaint", 12, 45, "Public post date."),
]
for i, s in enumerate(sig):
    t[29 + i] = R((s[0], 7), s[1], s[2], s[3])
t[33] = R(("Date confidence", 7), "Exact date x1.00, ceiling (may be a repost) x0.75, approximate x0.50.")

t[35] = [("Tier rules", 4)]
t[36] = [(h, 1) for h in ["Tier", "Minimum score", "Also needs"]]
tiers = [
    ("A", 70, "Pain of at least 15, a hiring or complaint signal, and a trigger from the last 90 days."),
    ("B", 50, "Pain of at least 5."),
    ("nurture", 30, "Fit alone, or a score between 30 and 50."),
    ("reject", 0, "Score below 30."),
]
for i, s in enumerate(tiers):
    t[37 + i] = R((s[0], 7), s[1], s[2])

t[42] = [(f"Source: data/scored.csv, written by scripts/score.py, run 2026-11-20. {N} accounts.", 6)]

grid1 = [t.get(r) for r in range(1, max(t) + 1)]
sheet1 = sheet_xml(grid1, [30, 42, 52, 34, 11, 9, 9, 10, 9],
                   merges=["A1:I1", "A2:I2", "A42:I42"])

# ---------- Tab 2: Accounts ----------
h2 = ["ICP", "Company", "Website", "Score", "Tier", "ICP match (/30)", "Pain (/40)", "Capacity (/15)",
      "Reachability (/15)", "Days since freshest signal", "Why this tier"]
grid2 = [[(h, 1) for h in h2]]
for r in rows:
    grid2.append([
        (r["icp"], 0), (r["company"], 7), (r["website"], 0),
        (float(r["score"]), 5), (r["tier"], 0),
        (float(r["icp_match"]), 5), (float(r["pain"]), 5), (float(r["capacity"]), 5),
        (float(r["reachability"]), 5), (int(r["freshest_days"]), 0), (r["reason"], 3),
    ])
sheet2 = sheet_xml(grid2, [11, 28, 32, 9, 10, 14, 11, 13, 15, 14, 80], freeze=1,
                   autofilter=f"A1:K{LAST}")

styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="0.0"/></numFmts>
<fonts count="5">
<font><sz val="10"/><name val="Arial"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
<font><b/><sz val="14"/><name val="Arial"/></font>
<font><b/><sz val="11"/><color rgb="FF1F3864"/><name val="Arial"/></font>
<font><b/><sz val="10"/><name val="Arial"/></font>
</fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/></patternFill></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="8">
<xf fontId="0" applyFont="1"><alignment vertical="top"/></xf>
<xf fontId="1" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf fontId="2" applyFont="1"/>
<xf fontId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf fontId="3" applyFont="1"/>
<xf fontId="0" numFmtId="164" applyFont="1" applyNumberFormat="1"><alignment vertical="top"/></xf>
<xf fontId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf fontId="4" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
</cellXfs>
</styleSheet>"""

ct = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
wb = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="ICP and Targeting" sheetId="1" r:id="rId1"/><sheet name="Accounts" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""
wbrels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", ct)
    z.writestr("_rels/.rels", rels)
    z.writestr("xl/workbook.xml", wb)
    z.writestr("xl/_rels/workbook.xml.rels", wbrels)
    z.writestr("xl/styles.xml", styles)
    z.writestr("xl/worksheets/sheet1.xml", sheet1)
    z.writestr("xl/worksheets/sheet2.xml", sheet2)
print(OUT, N, "accounts")
