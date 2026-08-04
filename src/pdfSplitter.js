const { PDFDocument } = require('pdf-lib');

/**
 * Splits a PDF buffer into an array of single-page PDF buffers, in page order.
 */
async function splitPdfIntoPages(pdfBuffer) {
  const srcDoc = await PDFDocument.load(pdfBuffer);
  const pageCount = srcDoc.getPageCount();

  const pageBuffers = [];
  for (let i = 0; i < pageCount; i++) {
    const newDoc = await PDFDocument.create();
    const [copiedPage] = await newDoc.copyPages(srcDoc, [i]);
    newDoc.addPage(copiedPage);
    const bytes = await newDoc.save();
    pageBuffers.push(Buffer.from(bytes));
  }

  return pageBuffers;
}

module.exports = { splitPdfIntoPages };
