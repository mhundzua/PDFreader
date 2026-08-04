const fs = require('fs');

// In-memory job registry. Fine for a single-instance deployment; jobs and
// their temp files are cleaned up automatically after MAX_AGE_MS.
const jobs = new Map();

const MAX_AGE_MS = 2 * 60 * 60 * 1000; // 2 hours

function createJob(id, initial) {
  const job = {
    id,
    status: 'uploaded', // uploaded -> processing -> done -> error
    createdAt: Date.now(),
    pageBuffers: [],
    results: [],
    processed: 0,
    total: 0,
    zipPath: null,
    summary: null,
    error: null,
    sseClients: new Set(),
    ...initial,
  };
  jobs.set(id, job);
  return job;
}

function getJob(id) {
  return jobs.get(id);
}

function deleteJob(id) {
  const job = jobs.get(id);
  if (!job) return;
  if (job.zipPath && fs.existsSync(job.zipPath)) {
    fs.unlink(job.zipPath, () => {});
  }
  for (const client of job.sseClients) {
    try { client.end(); } catch { /* ignore */ }
  }
  jobs.delete(id);
}

function cleanupStaleJobs() {
  const now = Date.now();
  for (const [id, job] of jobs) {
    if (now - job.createdAt > MAX_AGE_MS) {
      deleteJob(id);
    }
  }
}

setInterval(cleanupStaleJobs, 15 * 60 * 1000).unref();

module.exports = { createJob, getJob, deleteJob };
