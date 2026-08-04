const Anthropic = require('@anthropic-ai/sdk');

const MODEL = process.env.CLAUDE_MODEL || 'claude-sonnet-5';

let client = null;
function getClient() {
  if (!client) {
    if (!process.env.ANTHROPIC_API_KEY) {
      throw new Error('ANTHROPIC_API_KEY is not set on the server.');
    }
    client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  }
  return client;
}

const SYSTEM_PROMPT = `You are a document data extraction assistant. You will be shown a single scanned page from a form. \
Find these three fields on the page, if present:
- form_number: the form's number/ID (e.g. "DD-1234", "Form 27B", "AF-42"). Use exactly what is printed, keep letters, digits, and hyphens, no spaces.
- serial_number: a serial number, control number, or unique ID for this specific document instance (not the form number).
- date: the primary date on the page (signature date, form date, or issue date). Return it as ISO format YYYY-MM-DD. If only month/year is legible, use YYYY-MM-01.

Respond with ONLY raw JSON, no markdown fences, no commentary, in exactly this shape:
{"form_number": string or null, "serial_number": string or null, "date": string or null}

Use null for any field you cannot confidently read. Do not guess.`;

function extractJson(text) {
  const cleaned = text.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const start = cleaned.indexOf('{');
  const end = cleaned.lastIndexOf('}');
  if (start === -1 || end === -1) throw new Error('No JSON object found in model response');
  return JSON.parse(cleaned.slice(start, end + 1));
}

/**
 * Sends a single-page PDF buffer to Claude and asks it to extract
 * form_number, serial_number, and date from the page.
 * Returns { formNumber, serialNumber, date, raw } or throws on unrecoverable error.
 */
async function extractFieldsFromPage(pageBuffer, { maxRetries = 2 } = {}) {
  const anthropic = getClient();
  const base64 = pageBuffer.toString('base64');

  let lastErr;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await anthropic.messages.create({
        model: MODEL,
        max_tokens: 300,
        temperature: 0,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'document',
                source: {
                  type: 'base64',
                  media_type: 'application/pdf',
                  data: base64,
                },
              },
              {
                type: 'text',
                text: 'Extract form_number, serial_number, and date from this page as JSON.',
              },
            ],
          },
        ],
      });

      const textBlock = response.content.find((b) => b.type === 'text');
      if (!textBlock) throw new Error('No text content in Claude response');

      const parsed = extractJson(textBlock.text);
      return {
        formNumber: normalizeField(parsed.form_number),
        serialNumber: normalizeField(parsed.serial_number),
        date: normalizeDate(parsed.date),
      };
    } catch (err) {
      lastErr = err;
      const retryable = err?.status === 429 || err?.status >= 500 || err instanceof SyntaxError;
      if (!retryable || attempt === maxRetries) break;
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
    }
  }
  throw lastErr;
}

function normalizeField(value) {
  if (value === null || value === undefined) return null;
  const s = String(value).trim();
  return s.length ? s : null;
}

function normalizeDate(value) {
  if (!value) return null;
  const s = String(value).trim();
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  const [, year, month, day] = m;
  const y = Number(year), mo = Number(month), d = Number(day);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return `${year}-${month}-${day}`;
}

module.exports = { extractFieldsFromPage, MODEL };
