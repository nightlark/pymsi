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
    this.selectedFilesInfo = document.getElementById('selected-files-info');
    this.extractButton = document.getElementById('extract-button');
    this.extractStreamsButton = document.getElementById('extract-streams-button');
    this.exportTablesButton = document.getElementById('export-tables-button');
    this.exportFormatSelector = document.getElementById('export-format-selector');
    this.filesList = document.getElementById('files-list');
    this.tableSelector = document.getElementById('table-selector');
    this.tableHeader = document.getElementById('table-header');
    this.tableContent = document.getElementById('table-content');
    this.summaryContent = document.getElementById('summary-content');
    this.streamsContent = document.getElementById('streams-content');
    this.tabButtons = document.querySelectorAll('.tab-button');
    this.tabPanes = document.querySelectorAll('.tab-pane');
    this.loadExampleFileButton = document.getElementById('load-example-file-button');

    // Constants
    this.MAX_ERROR_DISPLAY_LENGTH = 500;
    this.DOWNLOAD_CLEANUP_DELAY_MS = 100; // Delay to ensure download initiates before cleanup

    // Disable file input and load example button initially while Pyodide is loading
    this.fileInput.disabled = true;
    this.loadExampleFileButton.disabled = true;
  }

  // Check if an error is related to missing cab files
  isMissingCabFileError(errorMessage) {
    // Check for various error patterns that indicate missing cab files:
    // 1. Custom ValueError: "External media file '...' not found"
    // 2. FileNotFoundError from resolve(strict=True): "FileNotFoundError" or "No such file or directory"
    // 3. Internal media file error: "Media file '...' not found in the .msi file"

    const hasExternalMediaError = errorMessage.includes('External media file') && errorMessage.includes('not found');
    const hasFileNotFoundError = errorMessage.includes('FileNotFoundError') || errorMessage.includes('No such file or directory');
    const hasInternalMediaError = errorMessage.includes('Media file') && errorMessage.includes('not found in the .msi file');

    return hasExternalMediaError || hasFileNotFoundError || hasInternalMediaError;
  }

  // Extract the missing cab filename from various error message formats
  extractMissingCabFileName(errorMessage) {
    // Try different patterns to extract the filename

    // Pattern 1: "External media file '...' not found"
    let match = errorMessage.match(/External media file '([^']+)' not found/);
    if (match) return match[1];

    // Pattern 2: "Media file '...' not found in the .msi file"
    match = errorMessage.match(/Media file '([^']+)' not found in the \.msi file/);
    if (match) return match[1];

    // Pattern 3: FileNotFoundError with path in the traceback
    // Look for common patterns like '/filename.cab' or 'filename.cab' in FileNotFoundError
    if (errorMessage.includes('FileNotFoundError') || errorMessage.includes('No such file or directory')) {
      // Try to find .cab file references in the error
      match = errorMessage.match(/['"]([^'"]*\.cab)['"]/i);
      if (match) return match[1];

      // Try to find path references ending in .cab
      match = errorMessage.match(/\/([^\s\/'"]+\.cab)/i);
      if (match) return match[1];
    }

    return null;
  }

  // Normalize path to use forward slashes and ensure it starts with /
  normalizePath(path) {
    const normalized = path.replace(/\\/g, '/');
    return normalized.startsWith('/') ? normalized : `/${normalized}`;
  }

  // Set up event listeners
  initEventListeners() {
    this.fileInput.addEventListener('change', this.handleFileSelect.bind(this));
    this.extractButton.addEventListener('click', this.extractFiles.bind(this));
    this.extractStreamsButton.addEventListener('click', this.extractStreams.bind(this));
    this.exportTablesButton.addEventListener('click', this.exportTables.bind(this));
    this.tableSelector.addEventListener('change', this.loadTableData.bind(this));

    // Tab switching
    this.tabButtons.forEach(button => {
      button.addEventListener('click', () => {
        const tabName = button.getAttribute('data-tab');
        this.switchTab(tabName);
      });
    });

    // New file loading buttons
    this.loadExampleFileButton.addEventListener('click', this.handleLoadExampleFile.bind(this));
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

      // Enable file input and load example button after successful initialization
      this.fileInput.disabled = false;
      this.loadExampleFileButton.disabled = false;
    } catch (error) {
      this.loadingIndicator.textContent = `Error loading Pyodide or pymsi: ${error.message}`;
      console.error('Error initializing:', error);
      // Keep buttons disabled if loading fails
    }
  }

  // Load MSI file from ArrayBuffer with optional additional files (used for file input, example, and URL)
  async loadMsiFileFromArrayBuffer(arrayBuffer, fileName = 'uploaded.msi', additionalFiles = []) {
    this.currentFileName = fileName;
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Reading MSI file...';

    // Store for potential retry with missing cab files
    this.lastMsiArrayBuffer = arrayBuffer;
    this.lastAdditionalFiles = additionalFiles;

    try {
      // Read the file as an ArrayBuffer
      const msiBinaryData = new Uint8Array(arrayBuffer);

      // Write the MSI file to Pyodide's virtual file system
      this.pyodide.FS.writeFile('/uploaded.msi', msiBinaryData);

      // Write additional files (e.g., .cab files) to the same directory
      if (additionalFiles && additionalFiles.length > 0) {
        this.loadingIndicator.textContent = `Writing ${additionalFiles.length} additional file(s)...`;
        for (const fileObj of additionalFiles) {
          const { data, name, path: customPath } = fileObj;
          const filePath = customPath || `/${name}`;
          // Create directory if path includes subdirectories
          if (filePath.includes('/') && filePath !== `/${name}`) {
            const dirPath = filePath.substring(0, filePath.lastIndexOf('/'));
            try {
              this.pyodide.FS.mkdirTree(dirPath);
            } catch (e) {
              // Only ignore EEXIST errors (directory already exists)
              if (!e.message || !e.message.includes('exists')) {
                console.error(`Failed to create directory ${dirPath}:`, e);
                throw e;
              }
              console.log(`Directory ${dirPath} already exists`);
            }
          }
          this.pyodide.FS.writeFile(filePath, new Uint8Array(data));
          console.log(`Wrote additional file: ${filePath}`);
        }
      }

      // Create Package and Msi objects using BytesIO to keep data in memory
      this.loadingIndicator.textContent = 'Processing MSI file...';
      // Pass the MSI data directly to Python instead of re-reading from filesystem
      this.pyodide.globals.set('msi_binary_data', msiBinaryData);
      await this.pyodide.runPythonAsync(`
        import io
        # Create BytesIO from the binary data passed from JavaScript
        msi_bytesio = io.BytesIO(bytes(msi_binary_data))
        # Create Package with BytesIO instead of Path to keep data in memory
        current_package = pymsi.Package(msi_bytesio)
        current_msi = pymsi.Msi(current_package, True)
      `);
      // Clean up the temporary global variable to prevent memory leaks
      this.pyodide.globals.delete('msi_binary_data');

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
      this.extractStreamsButton.disabled = false;
      this.exportTablesButton.disabled = false;
      this.exportFormatSelector.disabled = false;
      this.currentFileDisplay.textContent = `Currently loaded: ${this.currentFileName}`;
      this.currentFileDisplay.style.display = 'block';

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      console.error('Error processing MSI:', error);

      // Check if it's a missing external cab file error
      // The error message might be in a Pyodide traceback or a direct message
      const errorMessage = error.message || '';

      if (this.isMissingCabFileError(errorMessage)) {
        // Extract the missing file name from error message
        // Handle various error formats (ValueError, FileNotFoundError, etc.)
        const missingFileName = this.extractMissingCabFileName(errorMessage);

        if (missingFileName) {
          // Prompt user to select the missing file
          const shouldPrompt = await this.promptForMissingCabFile(missingFileName);
          if (shouldPrompt) {
            return; // Exit early, the prompt will handle retry
          }
        }

        // If we couldn't extract the filename or user cancelled, show error
        this.loadingIndicator.textContent = '';
        const errorText = document.createTextNode(`Error: Missing cabinet file`);
        this.loadingIndicator.appendChild(errorText);
        this.loadingIndicator.appendChild(document.createElement('br'));
        this.loadingIndicator.appendChild(document.createElement('br'));
        const tipText = document.createTextNode(`The MSI file references a cabinet file that was not found${missingFileName ? ': ' + missingFileName : ''}`);
        this.loadingIndicator.appendChild(tipText);
      } else {
        // For other errors, show the error message
        // Truncate very long tracebacks for display
        const displayMessage = errorMessage.length > this.MAX_ERROR_DISPLAY_LENGTH
          ? errorMessage.substring(0, this.MAX_ERROR_DISPLAY_LENGTH) + '...\n\n(Full error logged to console)'
          : errorMessage;
        this.loadingIndicator.textContent = `Error processing MSI file: ${displayMessage}`;
      }
    }
  }

  // Prompt user to select a missing cab file
  async promptForMissingCabFile(missingFileName) {
    return new Promise((resolve) => {
      // Clear loading indicator and show prompt
      this.loadingIndicator.textContent = '';
      this.loadingIndicator.style.display = 'block';

      const promptContainer = document.createElement('div');
      promptContainer.style.cssText = 'background: #fff3cd; border: 2px solid #ffc107; padding: 15px; border-radius: 6px; margin: 10px 0;';

      const messageText = document.createElement('p');
      messageText.style.cssText = 'margin: 0 0 10px 0; font-weight: 500;';
      messageText.textContent = `Missing cabinet file: ${missingFileName}`;
      promptContainer.appendChild(messageText);

      const instructionText = document.createElement('p');
      instructionText.style.cssText = 'margin: 0 0 15px 0; font-size: 0.9em;';
      instructionText.textContent = 'Please select the missing .cab file from your computer:';
      promptContainer.appendChild(instructionText);

      // Create file input
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = '.cab';
      fileInput.style.cssText = 'margin-bottom: 10px; display: block;';

      // Create buttons container
      const buttonsContainer = document.createElement('div');
      buttonsContainer.style.cssText = 'display: flex; gap: 10px; margin-top: 10px;';

      const loadButton = document.createElement('button');
      loadButton.textContent = 'Load File';
      loadButton.style.cssText = 'padding: 6px 12px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 500;';
      loadButton.disabled = true;

      const cancelButton = document.createElement('button');
      cancelButton.textContent = 'Cancel';
      cancelButton.style.cssText = 'padding: 6px 12px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;';

      buttonsContainer.appendChild(loadButton);
      buttonsContainer.appendChild(cancelButton);

      promptContainer.appendChild(fileInput);
      promptContainer.appendChild(buttonsContainer);
      this.loadingIndicator.appendChild(promptContainer);

      // Enable load button when file is selected
      fileInput.addEventListener('change', () => {
        loadButton.disabled = !fileInput.files || fileInput.files.length === 0;
      });

      // Handle load button click
      loadButton.addEventListener('click', async () => {
        if (fileInput.files && fileInput.files.length > 0) {
          const file = fileInput.files[0];
          const fileData = await file.arrayBuffer();

          // Determine the path for the cab file using utility function
          const cabPath = this.normalizePath(missingFileName);

          // Add to additional files and retry loading
          const newAdditionalFiles = this.lastAdditionalFiles ? [...this.lastAdditionalFiles] : [];
          newAdditionalFiles.push({
            name: file.name,
            data: fileData,
            path: cabPath
          });

          this.loadingIndicator.textContent = '';
          promptContainer.remove();

          // Retry loading with the new file
          await this.loadMsiFileFromArrayBuffer(this.lastMsiArrayBuffer, this.currentFileName, newAdditionalFiles);
          resolve(true);
        }
      });

      // Handle cancel button click
      cancelButton.addEventListener('click', () => {
        promptContainer.remove();
        this.loadingIndicator.textContent = 'Loading cancelled by user.';
        resolve(false);
      });
    });
  }

  // Handle file selection
  async handleFileSelect(event) {
    if (!this.fileInput.files || this.fileInput.files.length === 0) return;

    const files = Array.from(this.fileInput.files);

    // Find the MSI file
    const msiFile = files.find(f => f.name.toLowerCase().endsWith('.msi'));
    if (!msiFile) {
      this.loadingIndicator.style.display = 'block';
      this.loadingIndicator.textContent = 'Error: No .msi file selected. Please select an MSI file.';
      return;
    }

    // Get any additional files (e.g., .cab files)
    const additionalFiles = files.filter(f => f !== msiFile);

    // Check file sizes (warn if total > 500MB)
    const maxTotalSize = 500 * 1024 * 1024; // 500MB
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    if (totalSize > maxTotalSize) {
      console.warn(`Total file size (${Math.round(totalSize / 1024 / 1024)}MB) exceeds recommended limit (${Math.round(maxTotalSize / 1024 / 1024)}MB). Loading may be slow.`);
    }

    // Show info about selected files
    if (this.selectedFilesInfo) {
      if (additionalFiles.length > 0) {
        const fileList = additionalFiles.map(f => f.name).join(', ');
        this.selectedFilesInfo.textContent = `Selected: ${msiFile.name} + ${additionalFiles.length} additional file(s): ${fileList}`;
        this.selectedFilesInfo.style.display = 'block';
      } else {
        this.selectedFilesInfo.textContent = `Selected: ${msiFile.name}`;
        this.selectedFilesInfo.style.display = 'block';
      }
    }

    // Read all files
    const msiArrayBuffer = await msiFile.arrayBuffer();
    const additionalFilesData = await Promise.all(
      additionalFiles.map(async (file) => ({
        name: file.name,
        data: await file.arrayBuffer()
      }))
    );

    // Store for potential retry with missing cab files
    this.lastMsiArrayBuffer = msiArrayBuffer;
    this.lastAdditionalFiles = additionalFilesData;

    await this.loadMsiFileFromArrayBuffer(msiArrayBuffer, msiFile.name, additionalFilesData);
  }

  // Handle loading the example file from the server
  async handleLoadExampleFile() {
    const exampleUrl = '_static/example.msi';
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Fetching example file...';
    try {
      const response = await fetch(exampleUrl);
      if (!response.ok) throw new Error(`Failed to fetch example file (${response.status})`);
      const arrayBuffer = await response.arrayBuffer();
      await this.loadMsiFileFromArrayBuffer(arrayBuffer, 'example.msi');
    } catch (error) {
      this.loadingIndicator.textContent = `Error loading example file: ${error.message}`;
      console.error('Error loading example file:', error);
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

  // Get all stream names (not tables)
  async getAllStreamNames() {
    const streamNames = await this.pyodide.runPythonAsync(`
      streams = []
      for k in current_package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(k.name)
        if not is_table:
          streams.append(name)
      to_js(streams)
    `);
    return streamNames;
  }

  // Load streams information
  async loadStreams() {
    const streamsData = await this.getAllStreamNames();
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

      // Clean up after download starts
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, this.DOWNLOAD_CLEANUP_DELAY_MS);

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      this.loadingIndicator.textContent = `Error extracting files: ${error.message}`;
      console.error('Error extracting files:', error);
    }
  }

  // Extract all streams and create a ZIP for download
  async extractStreams() {
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Extracting streams...';

    try {
      // Get all stream names (including _StringPool and _StringData)
      const streamNames = await this.getAllStreamNames();

      if (streamNames.length === 0) {
        this.loadingIndicator.textContent = 'No streams found';
        setTimeout(() => {
          this.loadingIndicator.style.display = 'none';
        }, 2000);
        return;
      }

      this.loadingIndicator.textContent = 'Creating ZIP archive...';

      // Create ZIP file in JavaScript using JSZip library
      if (typeof JSZip === 'undefined') {
        throw new Error('JSZip failed to load.');
      }

      const zip = new JSZip();

      // Extract each stream
      for (const streamName of streamNames) {
        // Read the stream data using pymsi
        // Store streamName in Python globals to avoid string injection
        this.pyodide.globals.set('current_stream_name', streamName);
        const streamData = await this.pyodide.runPythonAsync(`
          import pymsi.streamname
          # Encode the stream name to get the internal OLE name
          encoded_name = pymsi.streamname.encode_unicode(current_stream_name, False)
          # Read the stream using a context manager to ensure proper cleanup
          with current_package.ole.openstream(encoded_name) as stream:
            stream_data = stream.read()
          to_js(stream_data)
        `);

        // Convert to Uint8Array with proper type checking
        let streamBytes;
        if (streamData instanceof Uint8Array) {
          streamBytes = streamData;
        } else if (ArrayBuffer.isView(streamData) || streamData instanceof ArrayBuffer) {
          streamBytes = new Uint8Array(streamData);
        } else if (Array.isArray(streamData)) {
          streamBytes = new Uint8Array(streamData);
        } else {
          throw new Error(`Unexpected stream data type for ${streamName}`);
        }
        
        // Add to ZIP with a safe filename
        zip.file(streamName, streamBytes);
      }

      // Generate ZIP blob
      const zipBlob = await zip.generateAsync({ type: 'blob' });

      // Create filename based on MSI name
      const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
      const zipFileName = `${baseFileName}_streams.zip`;

      // Trigger download
      const url = URL.createObjectURL(zipBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = zipFileName;
      document.body.appendChild(a);
      a.click();

      // Clean up after download starts
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, this.DOWNLOAD_CLEANUP_DELAY_MS);

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      this.loadingIndicator.textContent = `Error extracting streams: ${error.message}`;
      console.error('Error extracting streams:', error);
    }
  }

  // Get all table names, filtering out _StringPool and _StringData
  async getAllTableNames() {
    const tables = await this.pyodide.runPythonAsync(`
      tables = []
      for k in current_package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(k.name)
        if is_table and name not in ['_StringPool', '_StringData']:
          tables.append(name)
      to_js(tables)
    `);
    return tables;
  }

  // Get all data for a specific table
  async getTableData(tableName) {
    const tableData = await this.pyodide.runPythonAsync(`
      result = {'columns': [], 'rows': []}
      try:
        table = current_package.get('${tableName}')
        result['columns'] = [column.name for column in table.columns]
        result['rows'] = [row for row in table.rows]
      except Exception as e:
        print(f"Error getting table data: {e}")
      to_js(result)
    `);
    return tableData;
  }

  // Export tables in the selected format
  async exportTables() {
    const format = this.exportFormatSelector.value;
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Preparing table export...';

    try {
      const tableNames = await this.getAllTableNames();

      if (tableNames.length === 0) {
        this.loadingIndicator.textContent = 'No tables found to export';
        setTimeout(() => {
          this.loadingIndicator.style.display = 'none';
        }, 2000);
        return;
      }

      switch (format) {
        case 'csv':
          await this.exportAsCSV(tableNames);
          break;
        case 'xlsx':
          await this.exportAsExcel(tableNames);
          break;
        case 'sqlite':
          await this.exportAsSQLite(tableNames);
          break;
        case 'json':
          await this.exportAsJSON(tableNames);
          break;
        default:
          throw new Error(`Unsupported format: ${format}`);
      }

      this.loadingIndicator.style.display = 'none';
    } catch (error) {
      this.loadingIndicator.textContent = `Error exporting tables: ${error.message}`;
      console.error('Error exporting tables:', error);
    }
  }

  // Export all tables as CSV files in a ZIP
  async exportAsCSV(tableNames) {
    this.loadingIndicator.textContent = 'Exporting tables as CSV...';

    const zip = new JSZip();

    for (const tableName of tableNames) {
      const tableData = await this.getTableData(tableName);
      const columns = tableData.get('columns');
      const rows = tableData.get('rows');

      // Create CSV content
      let csvContent = columns.join(',') + '\n';

      for (const row of rows) {
        const values = columns.map(col => {
          const value = row.get(col);
          if (value === null || value === undefined) return '';
          // Escape quotes and wrap in quotes if contains comma, quote, or newline
          const strValue = String(value);
          if (strValue.includes(',') || strValue.includes('"') || strValue.includes('\n')) {
            return '"' + strValue.replace(/"/g, '""') + '"';
          }
          return strValue;
        });
        csvContent += values.join(',') + '\n';
      }

      zip.file(`${tableName}.csv`, csvContent);
    }

    const zipBlob = await zip.generateAsync({ type: 'blob' });
    const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
    const zipFileName = `${baseFileName}_tables.zip`;

    this.downloadBlob(zipBlob, zipFileName);
  }

  // Export all tables as an Excel workbook
  async exportAsExcel(tableNames) {
    this.loadingIndicator.textContent = 'Exporting tables as Excel...';

    if (typeof XLSX === 'undefined') {
      throw new Error('Excel library (SheetJS) not loaded');
    }

    const workbook = XLSX.utils.book_new();

    for (const tableName of tableNames) {
      const tableData = await this.getTableData(tableName);
      const columns = tableData.get('columns');
      const rows = tableData.get('rows');

      // Convert to array of arrays format for SheetJS
      const data = [columns];
      for (const row of rows) {
        const rowValues = columns.map(col => {
          const value = row.get(col);
          return value === null || value === undefined ? '' : value;
        });
        data.push(rowValues);
      }

      const worksheet = XLSX.utils.aoa_to_sheet(data);
      // Excel sheet names have a 31 character limit and can't contain: \ / ? * [ ] : '
      const sheetName = tableName.substring(0, 31).replace(/[:\\\/\?\*\[\]']/g, '_');
      XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
    }

    const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
    const blob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });

    const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
    const excelFileName = `${baseFileName}_tables.xlsx`;

    this.downloadBlob(blob, excelFileName);
  }

  // Export all tables as a SQLite database
  async exportAsSQLite(tableNames) {
    this.loadingIndicator.textContent = 'Exporting tables as SQLite...';

    if (typeof initSqlJs === 'undefined') {
      throw new Error('SQLite library (sql.js) not loaded');
    }

    const SQL = await initSqlJs({
      locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${file}`
    });

    const db = new SQL.Database();

    for (const tableName of tableNames) {
      const tableData = await this.getTableData(tableName);
      const columns = tableData.get('columns');
      const rows = tableData.get('rows');

      // Create table with all columns as TEXT to preserve original data without type conversion
      const columnDefs = columns.map(col => `"${col}" TEXT`).join(', ');
      const createTableSQL = `CREATE TABLE "${tableName}" (${columnDefs})`;
      db.run(createTableSQL);

      // Insert data
      if (rows.length > 0) {
        const placeholders = columns.map(() => '?').join(', ');
        const insertSQL = `INSERT INTO "${tableName}" VALUES (${placeholders})`;

        for (const row of rows) {
          const values = columns.map(col => {
            const value = row.get(col);
            return value === null || value === undefined ? null : String(value);
          });
          db.run(insertSQL, values);
        }
      }
    }

    const binaryArray = db.export();
    const blob = new Blob([binaryArray], { type: 'application/x-sqlite3' });

    const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
    const dbFileName = `${baseFileName}_tables.db`;

    this.downloadBlob(blob, dbFileName);
    db.close();
  }

  // Export all tables as JSON
  async exportAsJSON(tableNames) {
    this.loadingIndicator.textContent = 'Exporting tables as JSON...';

    const allTables = {};

    for (const tableName of tableNames) {
      const tableData = await this.getTableData(tableName);
      const columns = tableData.get('columns');
      const rows = tableData.get('rows');

      // Convert to plain JavaScript objects
      const tableRows = [];
      for (const row of rows) {
        const rowObj = {};
        for (const col of columns) {
          const value = row.get(col);
          rowObj[col] = value === null || value === undefined ? null : value;
        }
        tableRows.push(rowObj);
      }

      allTables[tableName] = tableRows;
    }

    const jsonString = JSON.stringify(allTables, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });

    const baseFileName = this.currentFileName.replace(/\.msi$/i, '');
    const jsonFileName = `${baseFileName}_tables.json`;

    this.downloadBlob(blob, jsonFileName);
  }

  // Helper function to download a blob
  downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    // Clean up after download starts
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, this.DOWNLOAD_CLEANUP_DELAY_MS);
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
