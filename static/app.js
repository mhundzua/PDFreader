const fileInput = document.getElementById("pdf-input");
const fileLabelText = document.getElementById("file-label-text");
const form = document.getElementById("upload-form");
const processBtn = document.getElementById("process-btn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const summaryStatsEl = document.getElementById("summary-stats");
const downloadLink = document.getElementById("download-link");
const pageTableBody = document.querySelector("#page-table tbody");
const errorEl = document.getElementById("error");

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileLabelText.textContent = file ? file.name : "Choose PDF";
  processBtn.disabled = !file;
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  resultsEl.hidden = true;
  errorEl.hidden = true;
  statusEl.hidden = false;
  statusEl.textContent = "Uploading and processing… this can take a minute or two for larger PDFs.";
  processBtn.disabled = true;

  const formData = new FormData();
  formData.append("pdf", file);

  try {
    const resp = await fetch("/upload", { method: "POST", body: formData });
    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.error || "Something went wrong.");
    }

    renderResults(data);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    statusEl.hidden = true;
    processBtn.disabled = false;
  }
});

function renderResults(data) {
  summaryStatsEl.innerHTML = "";

  const stats = [
    ["Pages processed", data.processed],
    ["Needs review", data.needs_review],
    ["Errors", data.errors],
  ];
  for (const [label, value] of stats) {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<span class="stat-value">${value}</span><span class="stat-label">${label}</span>`;
    summaryStatsEl.appendChild(div);
  }

  const foldersList = document.createElement("ul");
  foldersList.className = "folder-list";
  for (const f of data.folders) {
    const li = document.createElement("li");
    li.textContent = `${f.name}: ${f.count} file${f.count === 1 ? "" : "s"}`;
    foldersList.appendChild(li);
  }
  summaryStatsEl.appendChild(foldersList);

  downloadLink.href = data.download_url;

  pageTableBody.innerHTML = "";
  for (const p of data.pages) {
    const tr = document.createElement("tr");
    if (p.needs_review) tr.classList.add("needs-review");
    const notes = p.error ? `Error: ${p.error}` : p.needs_review ? "Missing data" : "";
    tr.innerHTML = `
      <td>${p.page_number}</td>
      <td>${p.folder}</td>
      <td>${p.filename || "-"}</td>
      <td>${notes}</td>
    `;
    pageTableBody.appendChild(tr);
  }

  resultsEl.hidden = false;
}
