require('dotenv').config();

const path = require('path');
const fs = require('fs');
const os = require('os');
const express = require('express');
const multer = require('multer');
const { v4: uuidv4 } = require('uuid');

const { splitPdfIntoPages } = require('./pdfSplitter');
const { extractFieldsFromPage } = require('./claudeExtractor');
const { organizeAndZip } = require('./organizer');
const { runWithConcurrency } = require('./pool');
const { createJob, getJob, deleteJob } = require('./jobStore');

const app = express();
const PORT = process.env.PORT || 3000;
const CLAUDE_CONCURRENCY = Number(process.env.CLAUDE_CONCURRENCY) || 3;
const TMP_DIR = path.join(os.tmpdir(), 'pdf-form-organizer');
fs.mkdirSync(TMP_DIR, { recursive: true });

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 75 * 1024 * 1024 }, // 75MB
  fileFilter: (req, file, cb) => {
    if (file.mimetype !== 'application/pdf') {
      return cb(new Error('Only PDF files are supported.'));
    }
    cb(null, true);
  },
});

app.use(express.static(path.join(__dirname, '..', 'public')));
app.use(express.json());

app.get('/api/health', (req, res) => {
  res.json({ ok: true, hasApiKey: Boolean(process.env.ANTHROPIC_API_KEY) });
});

app.post('/api/upload', upload.single('pdf'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No PDF file uploaded (field name "pdf").' });
    }

    const pageBuffers = await splitPdfIntoPages(req.file.buffer);
    if (pageBuffers.length === 0) {
      return res.status(400).json({ error: 'The PDF has no pages.' });
    }

    const jobId = uuidv4();
    createJob(jobId, {
      pageBuffers,
      total: pageBuffers.length,
      originalName: req.file.originalname,
    });

    res.json({ jobId, totalPages: pageBuffers.length });
  } catch (err) {
    console.error('Upload failed:', err);
    res.status(400).json({ error: err.message || 'Failed to read PDF.' });
  }
});

app.get('/api/process/:jobId', async (req, res) => {
  const job = getJob(req.params.jobId);
  if (!job) {
    return res.status(404).json({ error: 'Job not found or expired.' });
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });
  res.flushHeaders?.();

  const send = (event, data) => {
    res.write(`event: ${event}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  job.sseClients.add(res);
  req.on('close', () => job.sseClients.delete(res));

  if (job.status === 'done') {
    send('progress', { processed: job.total, total: job.total });
    send('done', { summary: job.summary, downloadUrl: `/api/download/${job.id}` });
    res.end();
    return;
  }
  if (job.status === 'error') {
    send('error', { error: job.error });
    res.end();
    return;
  }
  if (job.status === 'processing') {
    send('progress', { processed: job.processed, total: job.total });
    return; // stays open; will receive further events broadcast below
  }

  job.status = 'processing';
  send('progress', { processed: 0, total: job.total });

  const broadcast = (event, data) => {
    for (const client of job.sseClients) {
      client.write(`event: ${event}\n`);
      client.write(`data: ${JSON.stringify(data)}\n\n`);
    }
  };

  try {
    await runWithConcurrency(
      job.pageBuffers,
      CLAUDE_CONCURRENCY,
      async (buffer, index) => {
        try {
          const fields = await extractFieldsFromPage(buffer);
          return { pageIndex: index, buffer, ...fields, error: null };
        } catch (err) {
          console.error(`Page ${index + 1} extraction failed:`, err.message);
          return { pageIndex: index, buffer, formNumber: null, serialNumber: null, date: null, error: err.message };
        }
      },
      async (result) => {
        job.results.push(result);
        job.processed++;
        broadcast('progress', { processed: job.processed, total: job.total });
      }
    );

    const zipPath = path.join(TMP_DIR, `${job.id}.zip`);
    const summary = await organizeAndZip(job.results, zipPath);

    job.zipPath = zipPath;
    job.summary = summary;
    job.status = 'done';

    broadcast('done', { summary, downloadUrl: `/api/download/${job.id}` });
  } catch (err) {
    console.error('Processing failed:', err);
    job.status = 'error';
    job.error = err.message || 'Processing failed.';
    broadcast('error', { error: job.error });
  } finally {
    for (const client of job.sseClients) client.end();
    job.sseClients.clear();
    job.pageBuffers = []; // free memory; page buffers now live in job.results
  }
});

app.get('/api/download/:jobId', (req, res) => {
  const job = getJob(req.params.jobId);
  if (!job || !job.zipPath || !fs.existsSync(job.zipPath)) {
    return res.status(404).json({ error: 'File not found or expired.' });
  }
  res.download(job.zipPath, 'organized-forms.zip', (err) => {
    if (err) console.error('Download error:', err.message);
  });
});

app.delete('/api/job/:jobId', (req, res) => {
  deleteJob(req.params.jobId);
  res.json({ ok: true });
});

app.use((err, req, res, next) => {
  if (err instanceof multer.MulterError || err) {
    return res.status(400).json({ error: err.message });
  }
  next();
});

app.listen(PORT, () => {
  console.log(`PDF Form Organizer listening on http://localhost:${PORT}`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn('WARNING: ANTHROPIC_API_KEY is not set. Uploads will fail until it is configured.');
  }
});
