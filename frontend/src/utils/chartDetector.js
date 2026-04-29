/**
 * chartDetector.js
 * ─────────────────
 * Pure function that inspects a query result (columns + data rows)
 * and decides the best chart type, or returns null if no chart makes sense.
 *
 * Used by QueryPage.jsx to auto-render visualizations below the result table.
 *
 * Detection rules (in priority order):
 *   1.  No data / 1 col           → null  (table only)
 *   2.  1 row, 1 numeric          → kpi   (big number card)
 *   3.  1 date col + numeric cols → line  (time series)
 *   4.  2 text cols + 1 numeric   → groupedBar
 *   5.  1 text col + 1 numeric    → pie if rows ≤ 6, else bar
 *   6.  Anything else             → null  (table only)
 *
 * Returns:
 *   { type, config } where config has the column names the chart needs
 *   OR null if the data isn't chart-worthy
 */

// ─── HEURISTICS ──────────────────────────────────────────────────────────

// Column name patterns that look like identifiers, NOT quantitative values.
// These should never be plotted as a "value" axis even if they're numeric.
const ID_COLUMN_PATTERNS = [
  /^id$/i,
  /id$/i,             // ComID, AppId, UserID, etc.
  /^.*_id$/i,         // user_id, parent_id
  /code$/i,           // ApplicationCode
  /uuid/i,
  /guid/i,
];

// Column name patterns that signal a date/time axis.
const DATE_COLUMN_PATTERNS = [
  /date/i,
  /time/i,
  /^created/i,        // CreatedAt, CreatedOn
  /^updated/i,
  /^submitted/i,
  /day$/i,
  /month$/i,
];

// ─── COLUMN CLASSIFICATION ───────────────────────────────────────────────

/**
 * Classify a single column based on its name and sample values.
 * Returns: 'id' | 'date' | 'numeric' | 'text'
 */
function classifyColumn(columnName, sampleValues) {
  const name = String(columnName);

  // ID detection by name (highest priority — IDs masquerade as numbers)
  if (ID_COLUMN_PATTERNS.some((re) => re.test(name))) return 'id';

  // Date detection by name
  if (DATE_COLUMN_PATTERNS.some((re) => re.test(name))) return 'date';

  // Type detection by sample value
  // Filter out null/undefined for inspection
  const nonNull = sampleValues.filter((v) => v !== null && v !== undefined && v !== '');
  if (nonNull.length === 0) return 'text'; // empty column → treat as text

  const first = nonNull[0];

  // Numeric? — must be Number type AND not classified as ID above
  if (typeof first === 'number') return 'numeric';

  // String that parses as a date?
  if (typeof first === 'string') {
    // Quick date heuristic: ISO format, or contains - or /
    const looksLikeDate =
      /^\d{4}-\d{2}-\d{2}/.test(first) ||
      /^\d{2}\/\d{2}\/\d{4}/.test(first) ||
      /^\d{2}-[A-Za-z]{3}-\d{4}/.test(first);
    if (looksLikeDate) return 'date';

    // Identifier strings that LOOK numeric but aren't quantities:
    //   - phone numbers ("+916011236180", "+1-555-...")
    //   - leading-zero strings ("00123" — strips info if coerced)
    //   - long digit strings (>= 10 digits — likely IDs/phones, not measures)
    const looksLikeIdentifier =
      /^\+/.test(first) ||                // starts with +  → phone
      /^0\d/.test(first) ||               // leading zero    → preserved code
      /^\d{10,}$/.test(first.replace(/\D/g, '')); // 10+ digits → ID/phone
    if (looksLikeIdentifier) return 'text';

    // String that parses as a number? (DB sometimes returns numeric as string)
    if (!isNaN(Number(first)) && first.trim() !== '') return 'numeric';

    return 'text';
  }

  return 'text';
}

/**
 * Classify all columns in one pass.
 * Returns: { columnName: 'id' | 'date' | 'numeric' | 'text', ... }
 */
function classifyAllColumns(columns, data) {
  const classification = {};
  for (const col of columns) {
    const samples = data.slice(0, 5).map((row) => row[col]);
    classification[col] = classifyColumn(col, samples);
  }
  return classification;
}

// ─── MAIN DETECTOR ───────────────────────────────────────────────────────

/**
 * Decide the best chart for this result.
 *
 * @param {string[]} columns - column names in display order
 * @param {object[]} data    - array of row objects
 * @returns {object|null}    - { type, config } or null
 */
export function detectChart(columns, data) {
  // ─── Guard: no data, no chart
  if (!Array.isArray(data) || data.length === 0) return null;
  if (!Array.isArray(columns) || columns.length === 0) return null;

  // ─── Guard: too many columns to chart meaningfully
  if (columns.length > 4) return null;

  const types = classifyAllColumns(columns, data);

  const numericCols = columns.filter((c) => types[c] === 'numeric');
  const textCols = columns.filter((c) => types[c] === 'text');
  const dateCols = columns.filter((c) => types[c] === 'date');
  // idCols = columns.filter((c) => types[c] === 'id');  // intentionally excluded from charting

  // ─── Rule 1: KPI card — single row, single numeric value
  if (data.length === 1 && numericCols.length === 1 && columns.length <= 2) {
    return {
      type: 'kpi',
      config: {
        valueKey: numericCols[0],
        label: numericCols[0],
      },
    };
  }

  // ─── Rule 2: Line chart — date axis + numeric values
  if (dateCols.length === 1 && numericCols.length >= 1 && data.length >= 2) {
    return {
      type: 'line',
      config: {
        xKey: dateCols[0],
        yKeys: numericCols,
      },
    };
  }

  // ─── Rule 3: Grouped bar — 2 text dimensions + 1 numeric measure
  // (e.g. AppName + ServiceType + Count)
  if (textCols.length === 2 && numericCols.length === 1 && data.length >= 2) {
    return {
      type: 'groupedBar',
      config: {
        groupKey: textCols[0],   // outer grouping (e.g. AppName)
        seriesKey: textCols[1],  // inner series (e.g. ServiceType)
        valueKey: numericCols[0],
      },
    };
  }

  // ─── Rule 4: Pie or Bar — 1 text dimension + 1 numeric measure
  if (textCols.length === 1 && numericCols.length === 1 && data.length >= 2) {
    // Pie if few categories (≤ 6), bar otherwise
    const chartType = data.length <= 6 ? 'pie' : 'bar';
    return {
      type: chartType,
      config: {
        labelKey: textCols[0],
        valueKey: numericCols[0],
      },
    };
  }

  // ─── No clean chart fits → table only
  return null;
}

// ─── EXPORTS FOR TESTING ─────────────────────────────────────────────────
// Exposed so we can unit-test the helpers in isolation if needed.
export const __test__ = { classifyColumn, classifyAllColumns };