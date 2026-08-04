const fileInput = document.getElementById('pdf-input');
const filePickerLabel = document.getElementById('file-picker-label');
const startBtn = document.getElementById('start-btn');
const uploadError = document.getElementById('upload-error');

const uploadSection = document.getElementById('upload-section');
const progressSection = document.getElementById('progress-section');
const summarySection = document.getElementById('summary-section');
const errorSection = document.getElementById('error-section');

const progressFill = document.getElementById('progress-fill');
const progressLabel = document.getElementById('progress-label');

const summaryHeadline = document.getElementById('summary-headline');
const summaryFolders = document.getElementById('summary-folders');
const downloadBtn = document.getElementById('download-btn');

const errorMessage = document.getElementById('error-message');

let selectedFile = null;

fileInput.addEventListener('change', () => {
  selectedFile = fileInput.files[0] || null;
  filePickerLabel.textContent = selectedFile ? selectedFile.name : 'Choose or scan a PDF';
  startBtn.disabled = !selectedFile;
  hide(uploadError);
});

startBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  hide(uploadError);
  startBtn.disabled = true;

  try {
    const jobId = await uploadPdf(selectedFile);
    showSection(progressSection);
    listenForProgress(jobId);
  } catch (err) {
    startBtn.disabled = false;
    showError(uploadError, err.message);
  }
});

document.getElementById('reset-btn').addEventListener('click', resetApp);
document.getElementById('error-reset-btn').addEventListener('click', resetApp);

async function uploadPdf(file) {
  const formData = new FormData();
  formData.append('pdf', file);

  const res = await fetch('/api/upload', { method: 'POST', body: formData });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Upload failed.');
  return data.jobId;
}

function listenForProgress(jobId) {
  const source = new EventSource(`/api/process/${jobId}`);

  source.addEventListener('progress', (e) => {
    const { processed, total } = JSON.parse(e.data);
    updateProgress(processed, total);
  });

  source.addEventListener('done', (e) => {
    const { summary, downloadUrl } = JSON.parse(e.data);
    source.close();
    showSummary(summary, downloadUrl);
  });

  source.addEventListener('error', (e) => {
    source.close();
    let message = 'Processing failed.';
    if (e.data) {
      try { message = JSON.parse(e.data).error || message; } catch { /* ignore */ }
    }
    showSection(errorSection);
    errorMessage.textContent = message;
  });

  source.onerror = () => {
    // EventSource fires a generic error on connection issues too; only
    // surface it if we never reached a terminal state.
    if (source.readyState === EventSource.CLOSED) return;
  };
}

function updateProgress(processed, total) {
  const pct = total ? Math.round((processed / total) * 100) : 0;
  progressFill.style.width = `${pct}%`;
  progressLabel.textContent = `${processed} / ${total} pages`;
}

function showSummary(summary, downloadUrl) {
  showSection(summarySection);

  const parts = [`Processed ${summary.totalPages} page${summary.totalPages === 1 ? '' : 's'}.`];
  parts.push(`${summary.processedOk} organized successfully.`);
  if (summary.needsReview > 0) {
    parts.push(`${summary.needsReview} need review (missing form/serial/date).`);
  }
  summaryHeadline.textContent = parts.join(' ');

  summaryFolders.innerHTML = '';
  for (const { folder, count } of summary.monthFolders) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = folder;
    const count_ = document.createElement('span');
    count_.className = 'count';
    count_.textContent = `${count} file${count === 1 ? '' : 's'}`;
    li.append(name, count_);
    summaryFolders.appendChild(li);
  }
  if (summary.needsReview > 0) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = '_NeedsReview';
    const count_ = document.createElement('span');
    count_.className = 'count';
    count_.textContent = `${summary.needsReview} file${summary.needsReview === 1 ? '' : 's'}`;
    li.append(name, count_);
    summaryFolders.appendChild(li);
  }

  downloadBtn.href = downloadUrl;
}

function resetApp() {
  selectedFile = null;
  fileInput.value = '';
  filePickerLabel.textContent = 'Choose or scan a PDF';
  startBtn.disabled = true;
  updateProgress(0, 0);
  showSection(uploadSection);
}

function showSection(section) {
  for (const s of [uploadSection, progressSection, summarySection, errorSection]) {
    s.hidden = s !== section;
  }
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}

function hide(el) {
  el.hidden = true;
}
