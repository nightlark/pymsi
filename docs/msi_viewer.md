---
hide-toc: true
html_meta:
  description: Inspect Windows MSI installer files in your browser (no uploads). View summary metadata, tables/streams and extract files.
  keywords: MSI, Windows Installer, pymsi, Pyodide
  property=og:title: MSI Viewer & Extractor (pymsi)
  property=og:description: Inspect Windows MSI installer files in your browser (no uploads). View summary metadata, tables/streams and extract files.
  twitter:card: summary_large_image
  twitter:description: Inspect Windows MSI installer files in your browser (no uploads). View summary metadata, tables/streams and extract files.
  twitter:site: rmast
---

# MSI Viewer and Extractor

This interactive tool allows you to view the contents of MSI installer files directly in your browser. The processing happens *entirely on your device* - no files are uploaded to any server.

Behind the scenes, it is running [pymsi](https://github.com/nightlark/pymsi/) using Pyodide.

Like this tool and want to help out?

* Star the repo to support development: [nightlark/pymsi](https://github.com/nightlark/pymsi)
* Found a weird corner case or got feature ideas? [Open an issue](https://github.com/nightlark/pymsi/issues), [start a discussion](https://github.com/nightlark/pymsi/discussions), or [contribute](https://github.com/nightlark/pymsi/blob/main/CONTRIBUTING.md)!
* Share this page with coworkers or friends!

<div id="msi-viewer-app">
  <div class="toolbar">
    <button id="fullscreen-toggle" type="button" class="toolbar-btn">
      <span class="icon">⛶</span> Fullscreen
    </button>
  </div>
  <div class="file-selector">
    <div style="margin-bottom: 1rem;">
      <button id="load-example-file-button" type="button" class="example-file-btn" disabled>Load example file</button>
    </div>
    <div class="file-input-container">
      <input type="file" id="msi-file-input" accept=".msi,.cab,.zip" multiple disabled />
      <label for="msi-file-input" class="file-input-label">
        <span class="file-input-text">Choose MSI File</span>
        <span class="file-input-icon">📁</span>
      </label>
    </div>
    <div style="margin-top: 0.3rem; font-size: 0.85em; color: #666; text-align: center;">
      You can select multiple files at once if your MSI file references external .cab files<br>
      (or drag and drop an entire folder or ZIP archive containing an MSI installer)
    </div>
    <div id="selected-files-info" style="display: none; margin-top: 0.5rem; font-size: 0.9em; color: #555;"></div>
    <div id="loading-indicator" style="display: none;">Loading...</div>
  </div>

  <div id="msi-content">
    <div id="current-file-display" style="display: none;"></div>
    <div class="tabs">
      <button class="tab-button active" data-tab="files">Files</button>
      <button class="tab-button" data-tab="tables">Tables</button>
      <button class="tab-button" data-tab="summary">Summary</button>
      <button class="tab-button" data-tab="streams">Streams</button>
    </div>
    <div class="tab-content">
      <div id="files-tab" class="tab-pane active">
        <h3>Files</h3>
        <button id="extract-button" disabled>Extract All Files (ZIP)</button>
        <div id="files-list-container">
          <table id="files-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Directory</th>
                <th>Size</th>
                <th>Component</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody id="files-list">
              <tr><td colspan="5" class="empty-message">Select an MSI file to view its contents</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div id="tables-tab" class="tab-pane">
        <h3>Tables</h3>
        <div class="export-controls">
          <button id="export-tables-button" disabled>Export Tables</button>
          <select id="export-format-selector" disabled>
            <option value="csv">CSV (All tables, zipped)</option>
            <option value="xlsx">Excel Workbook (.xlsx)</option>
            <option value="sqlite">SQLite Database (.db)</option>
            <option value="json">JSON</option>
          </select>
        </div>
        <select id="table-selector"><option>Select an MSI file first</option></select>
        <div id="table-viewer-container">
          <table id="table-viewer">
            <thead id="table-header"></thead>
            <tbody id="table-content">
              <tr><td class="empty-message">Select an MSI file to view table data</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div id="summary-tab" class="tab-pane">
        <h3>Summary Information</h3>
        <div id="summary-content">
          <p class="empty-message">Select an MSI file to view summary information</p>
        </div>
      </div>
      <div id="streams-tab" class="tab-pane">
        <h3>Streams</h3>
        <button id="extract-streams-button" disabled>Extract All Streams (ZIP)</button>
        <div id="streams-content">
          <p class="empty-message">Select an MSI file to view streams</p>
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  #msi-viewer-app {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    max-width: 100%;
    margin: 0 auto;
    color: var(--msi-foreground);
    background: var(--msi-bg);
    --msi-bg: var(--color-background-primary, #ffffff);
    --msi-surface: var(--color-background-secondary, #f6f7fb);
    --msi-border: var(--color-background-border, #d5d8de);
    --msi-foreground: var(--color-foreground-primary, #1f2933);
    --msi-muted: var(--color-foreground-muted, #4b5563);
    --msi-accent: var(--color-brand-content, var(--color-link, #0066cc));
    --msi-accent-strong: var(--color-brand-primary, var(--color-link-hover, #0051a8));
    --msi-accent-border: #9bc4f5;
    --msi-accent-shadow: rgba(0, 102, 204, 0.18);
    --msi-overlay: var(--color-background-hover, #eef2f7);
    --msi-success: var(--color-success, #4caf50);
    --msi-success-muted: rgba(76, 175, 80, 0.16);
    --msi-disabled-surface: #eef1f5;
    --msi-accent-disabled: #dceaff;
    --msi-button-text: #ffffff;
  }

  #msi-viewer-app.fullscreen-mode {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    z-index: 2000;
    background: var(--msi-bg);
    padding: 2rem;
    overflow-y: auto;
    box-sizing: border-box;
  }

  .toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 0.5rem;
    max-width: 850px;
    margin-left: auto;
    margin-right: auto;
  }

  .toolbar-btn {
    background: transparent;
    border: 1px solid var(--msi-border);
    color: var(--msi-foreground);
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9em;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .toolbar-btn:hover {
    background: var(--msi-surface);
    color: var(--msi-accent);
    border-color: var(--msi-accent);
  }

  html[data-theme="dark"] #msi-viewer-app,
  body[data-theme="dark"] #msi-viewer-app {
    --msi-bg: var(--color-background-primary, #0f1115);
    --msi-surface: var(--color-background-secondary, #161a1f);
    --msi-border: var(--color-background-border, #2f3640);
    --msi-foreground: var(--color-foreground-primary, #e5e7eb);
    --msi-muted: var(--color-foreground-muted, #a0aec0);
    --msi-accent: var(--color-brand-content, var(--color-link, #7aa2f7));
    --msi-accent-strong: var(--color-brand-primary, var(--color-link-hover, #9bb4ff));
    --msi-accent-border: #4c6fbf;
    --msi-accent-shadow: rgba(122, 162, 247, 0.2);
    --msi-overlay: var(--color-background-hover, #1f2937);
    --msi-success: var(--color-success, #67e480);
    --msi-success-muted: rgba(103, 228, 128, 0.2);
    --msi-disabled-surface: #1a1e26;
    --msi-accent-disabled: rgba(122, 162, 247, 0.22);
  }

  @media (prefers-color-scheme: dark) {
    html:not([data-theme="light"]) #msi-viewer-app,
    body:not([data-theme="light"]) #msi-viewer-app {
      --msi-bg: var(--color-background-primary, #0f1115);
      --msi-surface: var(--color-background-secondary, #161a1f);
      --msi-border: var(--color-background-border, #2f3640);
      --msi-foreground: var(--color-foreground-primary, #e5e7eb);
      --msi-muted: var(--color-foreground-muted, #a0aec0);
      --msi-accent: var(--color-brand-content, var(--color-link, #7aa2f7));
      --msi-accent-strong: var(--color-brand-primary, var(--color-link-hover, #9bb4ff));
      --msi-accent-border: #4c6fbf;
      --msi-accent-shadow: rgba(122, 162, 247, 0.2);
      --msi-overlay: var(--color-background-hover, #1f2937);
      --msi-success: var(--color-success, #67e480);
      --msi-success-muted: rgba(103, 228, 128, 0.2);
      --msi-disabled-surface: #1a1e26;
      --msi-accent-disabled: rgba(122, 162, 247, 0.22);
    }
  }

  .file-selector {
    text-align: center;
    padding: 2rem;
    background: var(--msi-surface);
    border-radius: 8px;
    margin-bottom: 2rem;
    border: 1px solid var(--msi-border);
    max-width: 800px;
    margin-left: auto;
    margin-right: auto;
  }

  .file-input-container {
    position: relative;
    display: inline-flex;
    width: 100%;
    max-width: 320px;
  }

  .file-input-container.dragover .file-input-label {
    background: var(--msi-accent-strong);
    color: var(--msi-bg);
    border: 2px solid var(--msi-accent-border);
    box-shadow: 0 2px 16px 0 var(--msi-accent-shadow);
  }

  #msi-file-input {
    position: absolute;
    opacity: 0;
    width: 100%;
    height: 100%;
    left: 0;
    top: 0;
    z-index: 2;
    cursor: pointer;
  }

  .file-input-label {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: var(--msi-accent);
    color: var(--msi-bg);
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    transition: background-color 0.2s, box-shadow 0.2s, border 0.2s, color 0.2s;
    border: 2px solid transparent;
    box-shadow: none;
    position: relative;
    z-index: 1;
    width: 100%;
    min-width: 200px;
    min-height: 44px;
    text-align: center;
    user-select: none;
  }

  .file-input-label:hover,
  .file-input-container:hover .file-input-label,
  .file-input-label:focus-within {
    filter: brightness(90%);
    color: var(--msi-bg);
    border: 2px solid var(--msi-accent-border);
    box-shadow: 0 2px 12px 0 var(--msi-accent-shadow);
    outline: none;
  }

  #loading-indicator {
    margin-top: 1rem;
    padding: 0.5rem;
    background: var(--msi-overlay);
    border: 1px solid var(--msi-border);
    border-radius: 4px;
    color: var(--msi-accent);
    font-weight: 500;
  }

  #current-file-display {
    margin-bottom: 1rem;
    padding: 0.5rem 1rem;
    background: var(--msi-overlay);
    border: 1px solid var(--msi-border);
    border-radius: 4px;
    color: var(--msi-foreground);
    font-weight: 500;
    text-align: center;
  }

  .msi-content {
    width: min(95vw, 1920px);
    margin-left: auto;
    margin-right: auto;
  }

  .tabs {
    display: flex;
    margin-bottom: 0rem;
    border-bottom: 1px solid var(--msi-border);
  }

  .tab-button {
    background: var(--msi-overlay);
    border: 1px solid var(--msi-border);
    border-bottom: none;
    padding: 0.5rem 1rem;
    margin-right: 0.25rem;
    cursor: pointer;
    color: var(--msi-foreground);
    font-weight: 500;
  }

  .tab-button.active {
    background: var(--msi-bg);
    border-bottom: 1px solid var(--msi-bg);
    margin-bottom: -1px;
    color: var(--msi-accent-strong);
    box-shadow: inset 0 -2px 0 var(--msi-accent-strong);
  }

  .tab-button:not(.active):hover {
    background: var(--msi-surface);
    color: var(--msi-accent);
    border-color: var(--msi-border);
  }

  .tab-pane {
    display: none;
    padding: 1rem;
    border: 1px solid var(--msi-border);
    border-top: none;
  }

  .tab-pane.active {
    display: block;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th, td {
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--msi-border);
  }

  th.sortable {
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    padding-right: 1.6rem; /* reserve space for sort glyph */
  }

  th.sortable::after {
    content: attr(data-sort-indicator);
    display: inline-block;
    font-size: 0.8em;
    color: var(--msi-muted);
    margin-left: 0.35rem;
    width: 1em; /* fixed width to avoid layout shift */
  }

  #extract-button,
  #extract-streams-button {
    margin-bottom: 1rem;
    padding: 0.5rem 1rem;
    background: var(--msi-accent);
    color: var(--msi-bg);
    border: none;
    cursor: pointer;
    line-height: 1rem;
    height: 2rem;
  }

  #extract-button:disabled,
  #extract-streams-button:disabled {
  background: var(--msi-accent-disabled);
  color: var(--msi-muted);
  cursor: not-allowed;
  }

  .export-controls {
    margin-bottom: 1rem;
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  #export-tables-button {
    margin-bottom: 0;
    padding: 0.5rem 1rem;
    background: var(--msi-accent);
    color: var(--msi-bg);
    border: none;
    line-height: 1rem;
    height: 2rem;
  }

  #export-tables-button:not(:disabled) {
    cursor: pointer;
  }

  #export-tables-button:disabled {
    background: var(--msi-accent-disabled);
    color: var(--msi-muted);
    cursor: not-allowed;
  }

  #extract-button:hover:not(:disabled),
  #extract-streams-button:hover:not(:disabled),
  #export-tables-button:hover:not(:disabled) {
    filter: brightness(90%);
  }

  #table-selector,
  #export-format-selector {
    background-color: var(--msi-bg);
    color: var(--msi-foreground);
  }

  #export-format-selector {
    padding: 0.2rem;
    line-height: 1rem;
    height: 2rem;
  }

  #export-format-selector:disabled {
    background: var(--msi-surface);
    cursor: not-allowed;
  }

  .empty-message {
    text-align: center;
    color: var(--msi-muted);
    font-style: italic;
    padding: 2rem;
  }

  #files-list-container, #table-viewer-container {
    max-height: 500px;
    overflow-y: auto;
    border: 1px solid var(--msi-border);
  }

  .example-file-btn {
    font-size: 0.95em;
    padding: 0.3em 0.9em;
    background: var(--msi-surface);
    color: var(--msi-accent);
    border: 1px solid var(--msi-accent-border);
    border-radius: 4px;
    cursor: pointer;
    margin-bottom: 0.5rem;
    transition: background 0.2s, color 0.2s, border 0.2s;
    vertical-align: middle;
  }
  .example-file-btn:hover,
  .example-file-btn:focus {
    background: rgba(0, 102, 204, 0.1);
    color: var(--msi-accent-strong);
    border-color: var(--msi-accent-border);
    outline: none;
  }
  .example-file-btn:disabled {
    background: var(--msi-accent-disabled);
    color: var(--msi-muted);
    border-color: var(--msi-accent-border);
    cursor: not-allowed;
  }

  #msi-file-input:disabled {
    cursor: not-allowed;
  }

  #msi-file-input:disabled ~ .file-input-label {
    background: var(--msi-accent-disabled);
    color: var(--msi-muted);
    cursor: not-allowed;
    border-color: var(--msi-accent-border);
    box-shadow: none;
  }

  #msi-file-input:disabled ~ .file-input-label:hover,
  .file-input-container:hover #msi-file-input:disabled ~ .file-input-label {
    background: var(--msi-accent-disabled);
    color: var(--msi-muted);
    border-color: var(--msi-accent-border);
    box-shadow: none;
  }
</style>


<!-- Include the Pyodide script -->
<script type="text/javascript" src="https://cdn.jsdelivr.net/pyodide/v0.23.4/full/pyodide.js"></script>

<!-- Include JSZip script -->
<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>

<!-- Include SheetJS for Excel export -->
<script type="text/javascript" src="https://cdn.sheetjs.com/xlsx-0.20.2/package/dist/xlsx.full.min.js"></script>

<!-- Include sql.js for SQLite export -->
<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.min.js"></script>

<!-- Include the MSI viewer script with the correct path for ReadTheDocs -->
<script type="text/javascript" src="_static/msi_viewer.js"></script>
