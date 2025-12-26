# MSI Viewer and Extractor

This interactive tool allows you to view the contents of MSI files and extract their files directly in your browser. The processing happens entirely on your device - no files are uploaded to any server.

Behind the scenes, it is running [pymsi](https://github.com/nightlark/pymsi/) using Pyodide.

**Note:** Some MSI installers reference external `.cab` files. If your MSI file uses external cab files, you can select multiple files at once (the `.msi` file and any `.cab` files) to ensure all files can be extracted properly.

<div id="msi-viewer-app">
  <div class="file-selector">
    <div style="margin-bottom: 1rem;">
      <button id="load-example-file-button" type="button" class="example-file-btn">Load example file</button>
    </div>
    <div class="file-input-container">
      <input type="file" id="msi-file-input" accept=".msi,.cab" multiple />
      <label for="msi-file-input" class="file-input-label">
        <span class="file-input-text">Choose MSI File</span>
        <span class="file-input-icon">📁</span>
      </label>
    </div>
    <div style="margin-top: 0.3rem; font-size: 0.85em; color: #666; text-align: center;">
      You can also select .cab files if the MSI references external cabinet files
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
  }

  .file-selector {
    text-align: center;
    padding: 2rem;
    background: #f9f9f9;
    border-radius: 8px;
    margin-bottom: 2rem;
  }

  .file-input-container {
    position: relative;
    display: inline-flex;
    width: 100%;
    max-width: 320px;
  }

  .file-input-container.dragover .file-input-label {
    background: #005a9e;
    color: #e3f2fd;
    border: 2px solid #90caf9;
    box-shadow: 0 2px 16px 0 rgba(0, 122, 204, 0.22);
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
    background: #007acc;
    color: white;
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
    background: #005a9e;
    color: #e3f2fd;
    border: 2px solid #90caf9;
    box-shadow: 0 2px 12px 0 rgba(0, 122, 204, 0.18);
    outline: none;
  }

  #loading-indicator {
    margin-top: 1rem;
    padding: 0.5rem;
    background: #e3f2fd;
    border: 1px solid #90caf9;
    border-radius: 4px;
    color: #1565c0;
    font-weight: 500;
  }

  #current-file-display {
    margin-bottom: 1rem;
    padding: 0.5rem 1rem;
    background: #f0f8ff;
    border: 1px solid #b0d4f1;
    border-radius: 4px;
    color: #2c5282;
    font-weight: 500;
    text-align: center;
  }

  .tabs {
    display: flex;
    margin-bottom: 1rem;
    border-bottom: 1px solid #ddd;
  }

  .tab-button {
    background: #f5f5f5;
    border: 1px solid #ddd;
    border-bottom: none;
    padding: 0.5rem 1rem;
    margin-right: 0.25rem;
    cursor: pointer;
  }

  .tab-button.active {
    background: white;
    border-bottom: 1px solid white;
    margin-bottom: -1px;
  }

  .tab-pane {
    display: none;
    padding: 1rem;
    border: 1px solid #ddd;
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
    padding: 0.5rem;
    border-bottom: 1px solid #ddd;
  }

  #extract-button {
    margin-bottom: 1rem;
    padding: 0.5rem 1rem;
    background: #4CAF50;
    color: white;
    border: none;
    cursor: pointer;
  }

  #extract-button:disabled {
    background: #cccccc;
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
    background: #4CAF50;
    color: white;
    border: none;
  }

  #export-tables-button:not(:disabled) {
    cursor: pointer;
  }

  #export-tables-button:disabled {
    background: #cccccc;
    cursor: not-allowed;
  }

  #export-format-selector {
    padding: 0.5rem;
  }

  #export-format-selector:disabled {
    background: #f0f0f0;
    cursor: not-allowed;
  }

  .empty-message {
    text-align: center;
    color: #666;
    font-style: italic;
    padding: 2rem;
  }

  #files-list-container, #table-viewer-container {
    max-height: 500px;
    overflow-y: auto;
    border: 1px solid #ddd;
  }

  .example-file-btn {
    font-size: 0.95em;
    padding: 0.3em 0.9em;
    background: #f5f5f5;
    color: #007acc;
    border: 1px solid #b0d4f1;
    border-radius: 4px;
    cursor: pointer;
    margin-bottom: 0.5rem;
    transition: background 0.2s, color 0.2s, border 0.2s;
    vertical-align: middle;
  }
  .example-file-btn:hover,
  .example-file-btn:focus {
    background: #e3f2fd;
    color: #005a9e;
    border-color: #90caf9;
    outline: none;
  }
</style>
<script>
// filepath: pymsi/docs/msi_viewer.md (inline script)
document.addEventListener('DOMContentLoaded', function () {
  var fileInputContainer = document.querySelector('.file-input-container');
  var fileInput = document.getElementById('msi-file-input');
  if (!fileInputContainer || !fileInput) return;

  // Make the label and container clickable and droppable everywhere
  fileInputContainer.addEventListener('dragenter', function (e) {
    e.preventDefault();
    fileInputContainer.classList.add('dragover');
  });
  fileInputContainer.addEventListener('dragover', function (e) {
    e.preventDefault();
    fileInputContainer.classList.add('dragover');
  });
  fileInputContainer.addEventListener('dragleave', function (e) {
    if (e.relatedTarget && fileInputContainer.contains(e.relatedTarget)) return;
    fileInputContainer.classList.remove('dragover');
  });
  fileInputContainer.addEventListener('drop', function (e) {
    e.preventDefault();
    fileInputContainer.classList.remove('dragover');
    // If files are dropped, set them on the input and trigger change
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      // Trigger change event for compatibility
      var event = new Event('change', { bubbles: true });
      fileInput.dispatchEvent(event);
    }
  });
});
</script>

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
