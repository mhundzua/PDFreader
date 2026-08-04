const fs = require('fs');
const archiver = require('archiver');

const NEEDS_REVIEW_FOLDER = '_NeedsReview';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function sanitizeNamePart(value, fallback) {
  if (!value) return fallback;
  const cleaned = String(value)
    .trim()
    .replace(/[/\\:*?"<>|]/g, '')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
  return cleaned.length ? cleaned.slice(0, 80) : fallback;
}

function monthFolderName(isoDate) {
  const m = isoDate.match(/^(\d{4})-(\d{2})-\d{2}$/);
  if (!m) return null;
  const [, year, month] = m;
  const name = MONTH_NAMES[Number(month) - 1];
  return `${year}-${month} ${name}`;
}

/**
 * Decides the destination folder + base filename (without extension) for a
 * processed page based on the extracted fields.
 */
function planEntry(pageResult) {
  const { pageIndex, formNumber, serialNumber, date, error } = pageResult;
  const pageLabel = `page-${pageIndex + 1}`;

  if (error) {
    return { folder: NEEDS_REVIEW_FOLDER, baseName: `${pageLabel}_error`, needsReview: true };
  }

  const folder = date ? monthFolderName(date) : null;

  if (!formNumber || !serialNumber || !folder) {
    const formPart = sanitizeNamePart(formNumber, 'UnknownForm');
    const serialPart = sanitizeNamePart(serialNumber, 'UnknownSerial');
    return {
      folder: NEEDS_REVIEW_FOLDER,
      baseName: `${formPart}-${serialPart}_${pageLabel}`,
      needsReview: true,
    };
  }

  const formPart = sanitizeNamePart(formNumber, 'UnknownForm');
  const serialPart = sanitizeNamePart(serialNumber, 'UnknownSerial');
  return { folder, baseName: `${formPart}-${serialPart}`, needsReview: false };
}

/**
 * Writes a zip archive of the organized pages to outputPath.
 * pageResults: [{ pageIndex, buffer, formNumber, serialNumber, date, error }]
 * Returns a summary object describing what happened.
 */
async function organizeAndZip(pageResults, outputPath) {
  const usedNames = new Map(); // folder -> Set of used filenames
  const monthCounts = new Map(); // folder -> count
  let needsReviewCount = 0;

  const output = fs.createWriteStream(outputPath);
  const archive = archiver('zip', { zlib: { level: 9 } });

  const done = new Promise((resolve, reject) => {
    output.on('close', resolve);
    archive.on('error', reject);
  });
  archive.pipe(output);

  for (const result of pageResults.sort((a, b) => a.pageIndex - b.pageIndex)) {
    const { folder, baseName, needsReview } = planEntry(result);

    if (!usedNames.has(folder)) usedNames.set(folder, new Set());
    const namesInFolder = usedNames.get(folder);

    let finalName = `${baseName}.pdf`;
    let suffix = 2;
    while (namesInFolder.has(finalName)) {
      finalName = `${baseName} (${suffix}).pdf`;
      suffix++;
    }
    namesInFolder.add(finalName);

    archive.append(result.buffer, { name: `${folder}/${finalName}` });

    if (needsReview) {
      needsReviewCount++;
    } else {
      monthCounts.set(folder, (monthCounts.get(folder) || 0) + 1);
    }
  }

  await archive.finalize();
  await done;

  const totalPages = pageResults.length;
  const processedOk = totalPages - needsReviewCount;

  return {
    totalPages,
    processedOk,
    needsReview: needsReviewCount,
    monthFolders: Array.from(monthCounts.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([folder, count]) => ({ folder, count })),
  };
}

module.exports = { organizeAndZip, NEEDS_REVIEW_FOLDER };
