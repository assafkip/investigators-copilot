/**
 * CANONICAL REPORT TEMPLATE
 * Established: 2026-05-06 (from case-013 Leg 2 deliverable)
 * Updated:     2026-06-09 (synced from case-001-example generators)
 *
 * HOW TO USE:
 * 1. Copy this file to the target case's output/briefs/ directory
 * 2. Edit only the METADATA section below
 * 3. Replace the CONTENT SECTIONS with case findings
 * 4. Run: node generate-report.js
 *
 * DO NOT modify the helpers or document structure without updating this template.
 * This is the single source of truth for report formatting.
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, ImageRun, TableLayoutType
} = require("docx");

// ============================================================
// METADATA -- edit these per case, touch nothing else above
// ============================================================

const reportDate   = "Month DD, YYYY";           // e.g. "May 6, 2026"
const caseRef      = "Case NNN -- Subject Name"; // e.g. "Case 013 -- Pounds (Leg 2 Supplemental)"
const reportTitle  = "OSINT INVESTIGATION REPORT";
const reportSubtitle = "Subtitle / Matter Description"; // shown on cover under main title
const matterLine   = "Matter: Subject Name";     // e.g. "Matter: Example Online Attack Campaign"
const clientName   = "Client Full Name";          // e.g. "Example Client"
const headerLabel  = "CONFIDENTIAL -- OSINT Investigation Report"; // appears in page header

// Output filename and path -- adjust per case
const OUT_DIR  = path.join(__dirname); // override to case output/briefs/ when copying
const OUT_FILE = `OSINT_Report_CaseName_${reportDate.replace(/\s/g,"")}.docx`;

// ============================================================
// HELPERS -- do not edit
// ============================================================

const borderVisible = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const cellBorders   = { top: borderVisible, bottom: borderVisible, left: borderVisible, right: borderVisible };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 180 },
    children: [new TextRun({ text, bold: true, size: 30, color: "1B3A5C" })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 140 },
    children: [new TextRun({ text, bold: true, size: 26, color: "2E5A88" })]
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text, bold: true, size: 22, color: "2E5A88" })]
  });
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 140 },
    alignment: opts.align || AlignmentType.LEFT,
    children: [new TextRun({ text, size: 22, font: "Calibri", ...opts.run })]
  });
}

function pRuns(runs) {
  return new Paragraph({
    spacing: { after: 140 },
    children: runs.map(r => typeof r === "string"
      ? new TextRun({ text: r, size: 22, font: "Calibri" })
      : new TextRun({ size: 22, font: "Calibri", ...r }))
  });
}

function bullet(text, opts = {}) {
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 80 },
    children: [new TextRun({ text, size: 22, font: "Calibri", ...opts })]
  });
}

function bulletRuns(runs) {
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 80 },
    children: runs.map(r => typeof r === "string"
      ? new TextRun({ text: r, size: 22, font: "Calibri" })
      : new TextRun({ size: 22, font: "Calibri", ...r }))
  });
}

function subbullet(text) {
  return new Paragraph({
    bullet: { level: 1 },
    spacing: { after: 60 },
    children: [new TextRun({ text, size: 20, font: "Calibri" })]
  });
}

function quote(text) {
  return new Paragraph({
    spacing: { before: 120, after: 140 },
    indent: { left: 720, right: 720 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 12, color: "1B3A5C", space: 12 }
    },
    children: [new TextRun({ text, size: 22, font: "Calibri", italics: true, color: "333333" })]
  });
}

// widthPct: column width as percentage of page (e.g. 30 or 70)
// US Letter 1" margins = 9360 usable twips. Always pass columnWidths to new Table({}).
function tableHeaderCell(text, widthPct) {
  return new TableCell({
    width: { size: Math.round(widthPct / 100 * 9360), type: WidthType.DXA },
    borders: cellBorders,
    shading: { type: ShadingType.SOLID, color: "1B3A5C", fill: "1B3A5C" },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      spacing: { before: 60, after: 60 },
      children: [new TextRun({ text, bold: true, size: 20, color: "FFFFFF", font: "Calibri" })]
    })]
  });
}

function tableCell(text, widthPct, opts = {}) {
  return new TableCell({
    width: { size: Math.round(widthPct / 100 * 9360), type: WidthType.DXA },
    borders: cellBorders,
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({
      spacing: { before: 40, after: 40 },
      children: [new TextRun({
        text: String(text),
        size: 20,
        font: "Calibri",
        bold:    !!opts.bold,
        italics: !!opts.italics,
        color:   opts.color || "000000"
      })]
    })]
  });
}

// Read image dimensions from file header -- no external dep. Handles PNG and JPEG.
function readImageDimensions(filePath) {
  const buf = fs.readFileSync(filePath);
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".png") {
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  }
  if (ext === ".jpg" || ext === ".jpeg") {
    let i = 2;
    while (i < buf.length - 9) {
      if (buf[i] !== 0xFF) break;
      const marker = buf[i + 1];
      const segLen = buf.readUInt16BE(i + 2);
      if ((marker >= 0xC0 && marker <= 0xC3) || (marker >= 0xC5 && marker <= 0xC7) ||
          (marker >= 0xC9 && marker <= 0xCB) || (marker >= 0xCD && marker <= 0xCF)) {
        return { width: buf.readUInt16BE(i + 7), height: buf.readUInt16BE(i + 5) };
      }
      i += 2 + segLen;
    }
  }
  return { width: 800, height: 600 };
}

// Inline evidence image. item = { label, path, caption }.
// If path is missing or file absent, renders a red PENDING placeholder.
function inlineEvidence(item) {
  const DISPLAY_WIDTH = 580;
  const els = [];
  if (item.path && fs.existsSync(item.path)) {
    const { width, height } = readImageDimensions(item.path);
    const displayHeight = Math.round(height * DISPLAY_WIDTH / width);
    const ext = path.extname(item.path).toLowerCase();
    const imgType = (ext === ".jpg" || ext === ".jpeg") ? "jpg" : "png";
    els.push(new Paragraph({
      spacing: { before: 100, after: 60 },
      children: [new ImageRun({
        data: fs.readFileSync(item.path),
        transformation: { width: DISPLAY_WIDTH, height: displayHeight },
        type: imgType
      })]
    }));
  } else {
    els.push(new Paragraph({
      spacing: { before: 100, after: 60 },
      children: [new TextRun({
        text: `[SCREENSHOT PENDING: ${item.label} -- drop PNG into screenshots/ and re-run]`,
        size: 20, italics: true, color: "CC0000", font: "Calibri"
      })]
    }));
  }
  els.push(new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({ text: `Source: ${item.caption}`, size: 18, italics: true, color: "777777", font: "Calibri" })]
  }));
  return els;
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function spacer() {
  return new Paragraph({ spacing: { after: 160 }, children: [] });
}

// ============================================================
// EVIDENCE SCREENSHOT MANIFEST
// Each item: { label, path, caption }
// path: absolute path to PNG or JPEG. If absent -> red PENDING block.
// Sources:
//   extracted documents: path.join(__dirname, "..", "investigation", "evidence", "extracted", "<folder>", "images", "page-1.png")
//   manual captures:     path.join(__dirname, "screenshots", "<slug>.png")
// Use inlineEvidence(EVIDENCE_SCREENSHOTS[N]) to embed in the document.
// ============================================================

const SCREENSHOTS_DIR = path.join(__dirname, "screenshots");

const EVIDENCE_SCREENSHOTS = [
  // { label: "Description", path: path.join(SCREENSHOTS_DIR, "slug.png"), caption: "Source detail" },
];

// ============================================================
// TABLE PATTERN (canonical -- copy for every new Table)
//
//   new Table({
//     layout: TableLayoutType.FIXED,
//     width: { size: 9360, type: WidthType.DXA },
//     columnWidths: [Math.round(col1Pct / 100 * 9360), Math.round(col2Pct / 100 * 9360)],
//     rows: [
//       new TableRow({ children: [tableHeaderCell("Col 1", col1Pct), tableHeaderCell("Col 2", col2Pct)] }),
//       new TableRow({ children: [tableCell("value", col1Pct), tableCell("value", col2Pct)] }),
//     ]
//   })
//
// columnWidths MUST be set -- docx v9.6.1 defaults tblGrid to 100 per column
// which makes every column one character wide regardless of cell widths.
// ============================================================

// ============================================================
// DOCUMENT
// ============================================================

const doc = new Document({
  title: `OSINT Investigation Report -- ${caseRef}`,
  description: "CONFIDENTIAL",
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 22 } }
    }
  },
  sections: [{
    properties: {
      page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({
            text: headerLabel,
            italics: true, size: 16, color: "888888", font: "Calibri"
          })]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", size: 16, font: "Calibri", color: "888888" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, font: "Calibri", color: "888888" }),
            new TextRun({ text: " of ", size: 16, font: "Calibri", color: "888888" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, font: "Calibri", color: "888888" })
          ]
        })]
      })
    },
    children: [

      // ==================== COVER PAGE ====================
      new Paragraph({ spacing: { before: 2400 }, children: [] }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 240 },
        children: [new TextRun({ text: reportTitle, bold: true, size: 48, color: "1B3A5C", font: "Calibri" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 },
        children: [new TextRun({ text: reportSubtitle, size: 30, color: "555555", font: "Calibri" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 },
        children: [new TextRun({ text: matterLine, size: 26, bold: true, font: "Calibri" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 },
        children: [new TextRun({ text: `Case Reference: ${caseRef}`, size: 22, color: "666666", font: "Calibri" })]
      }),
      new Paragraph({ spacing: { before: 400 }, children: [] }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 },
        children: [new TextRun({ text: `Prepared for: ${clientName}`, size: 24, font: "Calibri" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
        children: [new TextRun({ text: `Date: ${reportDate}`, size: 24, font: "Calibri" })]
      }),
      new Paragraph({ spacing: { before: 600 }, children: [] }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
        children: [new TextRun({ text: "Classification: CONFIDENTIAL", size: 24, bold: true, color: "CC0000", font: "Calibri" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
        children: [new TextRun({
          text: "This report contains sensitive information compiled from public records and open-source databases. Distribution is limited to the named client and counsel of record.",
          size: 18, italics: true, color: "666666", font: "Calibri"
        })]
      }),
      pageBreak(),

      // ==================== CONTENT SECTIONS ====================
      // Replace everything below this line with case-specific content.
      // Use the helpers above: h1(), h2(), h3(), p(), pRuns(), bullet(),
      // bulletRuns(), subbullet(), quote(), tableHeaderCell(), tableCell(),
      // inlineEvidence(), pageBreak(), spacer()
      //
      // Recommended section order:
      //   h1("Executive Summary")
      //   h2("Key Judgments")     -- bulletRuns() with KJ-N bold labels
      //   h2("Recommended Counsel Actions")
      //   pageBreak()
      //   h1("Section 1. ...")   -- one h1 per major finding / objective
      //   ...
      //   pageBreak()
      //   h1("Appendix A. Evidence Registry / Data Sources")
      //   h1("Appendix B. Methodology and Limitations")
      //   -- End marker (centered italic p) --

      h1("Executive Summary"),
      p("PLACEHOLDER -- replace with case executive summary."),

      pageBreak(),
      h1("Appendix A. Evidence Registry"),
      p("PLACEHOLDER -- replace with evidence table."),

      pageBreak(),
      h1("Appendix B. Methodology and Limitations"),
      p("PLACEHOLDER -- replace with methodology notes."),

      new Paragraph({ spacing: { before: 400 }, children: [] }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "-- End of Report --", size: 20, italics: true, color: "888888", font: "Calibri" })]
      }),

    ]
  }]
});

// ============================================================
// WRITE
// ============================================================

const outPath = path.join(OUT_DIR, OUT_FILE);

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outPath, buffer);
  console.log("Wrote: " + outPath);
  console.log("Size:  " + (buffer.length / 1024).toFixed(1) + " KB");
}).catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
