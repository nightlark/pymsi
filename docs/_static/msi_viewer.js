// MSI Viewer JavaScript Implementation

// Main class for the MSI Viewer application
class MSIViewer {
  constructor() {
    this.pyodide = null;
    this.pymsi = null;
    this.currentPackage = null;
    this.currentMsi = null;
    this.currentFileName = null;
    this.initElements();
    this.initEventListeners();
    this.loadPyodide();
  }

  // Initialize DOM element references
  initElements() {
    this.fileInput = document.getElementById('msi-file-input');
    this.loadingIndicator = document.getElementById('loading-indicator');
    this.msiContent = document.getElementById('msi-content');
    this.currentFileDisplay = document.getElementById('current-file-display');
    this.extractButton = document.getElementById('extract-button');
    this.filesList = document.getElementById('files-list');
    this.tableSelector = document.getElementById('table-selector');
    this.tableHeader = document.getElementById('table-header');
    this.tableContent = document.getElementById('table-content');
    this.summaryContent = document.getElementById('summary-content');
    this.streamsContent = document.getElementById('streams-content');
    this.tabButtons = document.querySelectorAll('.tab-button');
    this.tabPanes = document.querySelectorAll('.tab-pane');
  }

  // Set up event listeners
  initEventListeners() {
    this.fileInput.addEventListener('change', this.handleFileSelect.bind(this));
    this.extractButton.addEventListener('click', this.extractFiles.bind(this));
    this.tableSelector.addEventListener('change', this.loadTableData.bind(this));

    // Tab switching
    this.tabButtons.forEach(button => {
      button.addEventListener('click', () => {
        const tabName = button.getAttribute('data-tab');
        this.switchTab(tabName);
      });
    });
  }

  // Switch between tabs
  switchTab(tabName) {
    this.tabButtons.forEach(button => {
      button.classList.toggle('active', button.getAttribute('data-tab') === tabName);
    });

    this.tabPanes.forEach(pane => {
      const isActive = pane.id === `${tabName}-tab`;
      pane.classList.toggle('active', isActive);
    });
  }

  // Load Pyodide and pymsi
  async loadPyodide() {
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Loading Pyodide...';

    try {
      // Pyodide should already be loaded from the script in the HTML
      if (typeof loadPyodide === 'undefined') {
        throw new Error('Pyodide is not loaded. Please check your internet connection.');
      }

      this.pyodide = await loadPyodide();
      if (!this.pyodide) {
        throw new Error('loadPyodide() failed.');
      }

      this.loadingIndicator.textContent = 'Loading pymsi...';

      // Install pymsi using micropip
      await this.pyodide.loadPackagesFromImports('import micropip');
      const micropip = this.pyodide.pyimport('micropip');
      // The name of the package is 'python-msi' on PyPI
      await micropip.install('python-msi');

      // Import pymsi
      await this.pyodide.runPythonAsync(`
        import pymsi
        import json
        import io
        import zipfile
        from js import Uint8Array, Object, File, Blob, URL
        from pyodide.ffi import to_js
      `);

      this.pymsi = this.pyodide.pyimport('pymsi');
      this.loadingIndicator.style.display = 'none';
      console.log('pymsi loaded successfully');
    } catch (error) {
      this.loadingIndicator.textContent = `Error loading Pyodide or pymsi: ${error.message}`;
      console.error('Error initializing:', error);
    }
  }

  // Handle file selection
  async handleFileSelect(event) {
    if (!this.fileInput.files || this.fileInput.files.length === 0) return;

    const file = this.fileInput.files[0];
    this.currentFileName = file.name;
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Reading MSI file...';

    try {
      // Read the file as an ArrayBuffer
      const arrayBuffer = await file.arrayBuffer();
      const msiBinaryData = new Uint8Array(arrayBuffer);

      // Write the file to Pyodide's virtual file system
      this.pyodide.FS.writeFile('/uploaded.msi', msiBinaryData);

      // Create Package and Msi objects using the file path
      await this.pyodide.runPythonAsync(`
        from pathlib import Path
        current_package = pymsi.Package(Path('/uploaded.msi'))
        current_msi = pymsi.Msi(current_package, True)
      `);

      this.currentPackage = await this.pyodide.globals.get('current_package');
      this.currentMsi = await this.pyodide.globals.get('current_msi');
      console.log('Successfully created MSI object:', this.currentMsi);
      console.log('Successfully created Package object:', this.currentPackage);

      // Load and display the MSI contents
      await this.loadFilesList();
      console.log('Files list loaded successfully');
      await this.loadTablesList();
      console.log('Tables list loaded successfully');
      await this.loadSummaryInfo();
      console.log('Summary information loaded successfully');
      await this.loadStreams();
      console.log('Streams loaded successfully');

      // Enable the extract button and show current file
      this.extractButton.disabled = false;
      this.currentFileDisplay.textContent = `Currently loaded: ${this.currentFileName}`;
      this.currentFileDisplay.style.display = 'block';

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      this.loadingIndicator.textContent = `Error processing MSI file: ${error.message}`;
      console.error('Error processing MSI:', error);
    }
  }

  // Load files list from MSI
  async loadFilesList() {
    const filesData = await this.pyodide.runPythonAsync(`
      files = []
      try:
        for file in current_msi.files.values():
          files.append({
            'name': file.name,
            'directory': file.component.directory.name,
            'size': file.size,
            'component': file.component.id,
            'version': file.version
          })
      except Exception as e:
        print(f"Error getting files: {e}")
        files = []
      to_js(files)
    `);
    console.log('Files data loaded:', filesData);

    this.filesList.innerHTML = '';

    if (filesData.length === 0) {
      this.filesList.innerHTML = '<tr><td colspan="5">No files found</td></tr>';
      return;
    }

    for (const file of filesData) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${file.get("name") || ''}</td>
        <td>${file.get("directory") || ''}</td>
        <td>${file.get("size") || ''}</td>
        <td>${file.get("component") || ''}</td>
        <td>${file.get("version") || ''}</td>
      `;
      this.filesList.appendChild(row);
    }
  }

  // Load tables list
  async loadTablesList() {
    const tables = await this.pyodide.runPythonAsync(`
      tables = []
      for k in current_package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(k.name)
        if is_table:
          tables.append(name)
      to_js(tables)
    `);
    console.log('Tables found:', tables);

    this.tableSelector.innerHTML = '';

    if (tables.length === 0) {
      this.tableSelector.innerHTML = '<option>No tables found</option>';
      return;
    }

    tables.forEach(table => {
      const option = document.createElement('option');
      option.value = table;
      option.textContent = table;
      this.tableSelector.appendChild(option);
    });

    // Load the first table by default
    if (tables.length > 0) {
      this.loadTableData();
    }
  }

  // Load table data when a table is selected
  async loadTableData() {
    const selectedTable = this.tableSelector.value;
    if (!selectedTable) return;

    const tableData = await this.pyodide.runPythonAsync(`
      result = {'columns': [], 'rows': []}
      try:
        table = current_package.get('${selectedTable}')
        result['columns'] = [column.name for column in table.columns]
        result['rows'] = [row for row in table.rows]
      except Exception as e:
        print(f"Error getting table data: {e}")
      to_js(result)
    `);
    console.log('Table data loaded:', tableData);

    // Display table columns
    this.tableHeader.innerHTML = '';
    const headerRow = document.createElement('tr');

    for (const column of tableData.get("columns")) {
      const th = document.createElement('th');
      th.textContent = column;
      headerRow.appendChild(th);
    }

    this.tableHeader.appendChild(headerRow);

    // Display table rows
    this.tableContent.innerHTML = '';

    if (tableData.get("rows").length === 0) {
      const emptyRow = document.createElement('tr');
      emptyRow.innerHTML = `<td colspan="${tableData.get("columns").length}">No data</td>`;
      this.tableContent.appendChild(emptyRow);
      return;
    }

    for (const rowData of tableData.get("rows")) {
      const row = document.createElement('tr');

      // Iterate through columns to maintain the correct order
      for (const column of tableData.get("columns")) {
        const td = document.createElement('td');
        const value = rowData.get(column);
        td.textContent = (value !== null && value !== undefined) ? String(value) : '';
        row.appendChild(td);
      }

      this.tableContent.appendChild(row);
    }
  }

  // Load summary information
  async loadSummaryInfo() {
    const summaryData = await this.pyodide.runPythonAsync(`
      result = {}
      summary = current_package.summary

      # Helper function to safely convert values to string
      def safe_str(value):
        return "" if value is None else str(value)

      # Add each property if it exists
      result["arch"] = safe_str(summary.arch())
      result["author"] = safe_str(summary.author())
      result["comments"] = safe_str(summary.comments())
      result["creating_application"] = safe_str(summary.creating_application())
      result["creation_time"] = safe_str(summary.creation_time())
      result["languages"] = safe_str(summary.languages())
      result["subject"] = safe_str(summary.subject())
      result["title"] = safe_str(summary.title())
      result["uuid"] = safe_str(summary.uuid())
      result["word_count"] = safe_str(summary.word_count())

      to_js(result)
    `);
    console.log('Summary data loaded:', summaryData);

    this.summaryContent.innerHTML = '';

    if (summaryData.size === 0) {
      this.summaryContent.innerHTML = '<p>No summary information available</p>';
      return;
    }

    const table = document.createElement('table');

    for (const [key, value] of summaryData) {
      const row = document.createElement('tr');
      const keyCell = document.createElement('td');
      const valueCell = document.createElement('td');

      keyCell.textContent = key;
      valueCell.textContent = value !== null ? String(value) : '';

      row.appendChild(keyCell);
      row.appendChild(valueCell);
      table.appendChild(row);
    }

    this.summaryContent.appendChild(table);
  }

  // Load streams information
  async loadStreams() {
    const streamsData = await this.pyodide.runPythonAsync(`
      streams = []
      for k in current_package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(k.name)
        if not is_table:
          streams.append(name)
      to_js(streams)
    `);
    console.log('Streams data loaded:', streamsData);

    this.streamsContent.innerHTML = '';

    if (streamsData.length === 0) {
      this.streamsContent.innerHTML = '<p>No streams available</p>';
      return;
    }

    const table = document.createElement('table');
    const headerRow = document.createElement('tr');
    headerRow.innerHTML = '<th>Name</th>';
    table.appendChild(headerRow);

    for (const stream of streamsData) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${stream}</td>
      `;
      table.appendChild(row);
    }

    this.streamsContent.appendChild(table);
  }

  // Extract files and create a ZIP for download
  async extractFiles() {
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Extracting files...';

    try {
      // Import and use the extract_root function from __main__.py
      await this.pyodide.runPythonAsync(`
        import shutil
        from pathlib import Path
        from pymsi.__main__ import extract_root

        # Clean up and recreate temp directory
        temp_dir = Path('/tmp/extracted')
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Extract files using the same logic as the CLI
        extract_root(current_msi.root, temp_dir)
      `);

      this.loadingIndicator.textContent = 'Creating ZIP archive...';

      // Get list of all extracted files
      const fileList = await this.pyodide.runPythonAsync(`
        import os
        files = []
        temp_dir = Path('/tmp/extracted')
        for root, dirs, filenames in os.walk(temp_dir):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, temp_dir)
                files.append(rel_path)
        to_js(files)
      `);

      if (fileList.length === 0) {
        this.loadingIndicator.textContent = 'No files extracted';
        setTimeout(() => {
          this.loadingIndicator.style.display = 'none';
        }, 2000);
        return;
      }

      // Create ZIP file in JavaScript using JSZip library
      // We need to make sure JSZip is loaded
      if (typeof JSZip === 'undefined') {
        throw new Error('JSZip failed to load.');
      }

      const zip = new JSZip();

      // Add each file to the ZIP
      for (const filePath of fileList) {
        const fileData = this.pyodide.FS.readFile(`/tmp/extracted/${filePath}`);
        zip.file(filePath, fileData);
      }

      // Generate ZIP blob
      const zipBlob = await zip.generateAsync({ type: 'blob' });

      // Create filename based on MSI name
      const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
      const zipFileName = `${baseFileName}_extracted.zip`;

      // Trigger download
      const url = URL.createObjectURL(zipBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = zipFileName;
      document.body.appendChild(a);
      a.click();

      // Clean up
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 0);

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      this.loadingIndicator.textContent = `Error extracting files: ${error.message}`;
      console.error('Error extracting files:', error);
    }
  }
}

// Initialize the MSI Viewer when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Check if we're in the MSI viewer page
  console.log('Initializing MSI Viewer...');
  if (document.getElementById('msi-viewer-app')) {
    // Pyodide is already loaded via the script in the HTML
    setTimeout(() => {
      new MSIViewer();
    }, 100);
  } else {
    console.warn('MSI Viewer app not found in the DOM. Make sure you are on the correct page.');
  }
});
