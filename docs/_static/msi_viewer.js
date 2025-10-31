// MSI Viewer JavaScript Implementation
//
// This application uses Web Workers to handle MSI processing in a background thread,
// preventing the main UI thread from blocking during long operations like:
// - Loading and initializing Pyodide
// - Parsing large MSI files
// - Extracting files with LZX compression
//
// Architecture:
// - Main thread: Handles UI updates, user interactions, and rendering
// - Worker thread: Handles Pyodide and all MSI processing operations
// - Communication: postMessage API for bidirectional messaging

// Main class for the MSI Viewer application
class MSIViewer {
  constructor() {
    // Configuration constants
    this.WORKER_PATH = '_static/msi_viewer_worker.js';
    this.WORKER_INIT_MAX_RETRIES = 10;
    this.WORKER_INIT_BASE_DELAY = 500;
    this.WORKER_INIT_MAX_DELAY = 5000;
    this.WORKER_INIT_BACKOFF_FACTOR = 1.5;
    
    this.worker = null;
    this.currentFileName = null;
    this.tablesData = [];
    this.isWorkerReady = false;
    this._loadRetries = 0;
    this._loadRetryTimeout = null;
    this.initElements();
    this.initEventListeners();
    this.initWorker();
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
    this.loadExampleFileButton = document.getElementById('load-example-file-button');
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

  // Initialize the web worker
  initWorker() {
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Initializing...';
    this.loadingIndicator.classList.remove('error');

    try {
      // Create worker - path is relative to the HTML page location
      // This works correctly on ReadTheDocs where the HTML is at /en/latest/msi_viewer.html
      // and the worker is at /en/latest/_static/msi_viewer_worker.js
      this.worker = new Worker(this.WORKER_PATH);

      // Handle messages from the worker
      this.worker.addEventListener('message', (event) => {
        this.handleWorkerMessage(event.data);
      });

      // Handle worker errors
      this.worker.addEventListener('error', (error) => {
        console.error('Worker error:', error);
        this.loadingIndicator.classList.add('error');
        this.loadingIndicator.textContent = `Worker error: ${error.message}`;
      });

      // Initialize Pyodide in the worker
      this.worker.postMessage({ type: 'init' });
    } catch (error) {
      console.error('Error creating worker:', error);
      this.loadingIndicator.classList.add('error');
      this.loadingIndicator.textContent = `Error creating worker: ${error.message}`;
    }
  }

  // Handle messages from the worker
  handleWorkerMessage(message) {
    const { type, success, error, data, message: progressMsg, isError } = message;

    switch (type) {
      case 'progress':
        this.loadingIndicator.style.display = 'block';
        this.loadingIndicator.textContent = progressMsg;
        if (isError) {
          this.loadingIndicator.classList.add('error');
          console.error('Worker progress error:', progressMsg);
        } else {
          this.loadingIndicator.classList.remove('error');
        }
        break;

      case 'initialized':
        if (success) {
          this.isWorkerReady = true;
          this.loadingIndicator.style.display = 'none';
          this.loadingIndicator.classList.remove('error');
          console.log('Worker initialized successfully');
        } else {
          this.loadingIndicator.classList.add('error');
          this.loadingIndicator.textContent = `Initialization error: ${error}`;
          console.error('Worker initialization failed:', error);
        }
        break;

      case 'msi-loaded':
        this.loadingIndicator.classList.remove('error');
        if (success) {
          this.displayMsiData(data, message.fileName);
        } else {
          this.loadingIndicator.classList.add('error');
          this.loadingIndicator.textContent = `Error loading MSI: ${error}`;
          console.error('MSI loading failed:', error);
        }
        break;

      case 'table-data':
        this.loadingIndicator.classList.remove('error');
        if (success) {
          this.displayTableData(data);
        } else {
          this.loadingIndicator.classList.add('error');
          this.loadingIndicator.textContent = `Error loading table: ${error}`;
          console.error('Table loading failed:', error);
        }
        break;

      case 'extract-complete':
        this.loadingIndicator.classList.remove('error');
        if (success) {
          this.createZipFromExtractedFiles(message.files, message.baseFileName);
        } else {
          this.loadingIndicator.classList.add('error');
          this.loadingIndicator.textContent = `Extraction error: ${error}`;
          console.error('Extraction failed:', error);
        }
        break;

      default:
        console.warn('Unknown message type from worker:', type);
    }
  }

  // Display MSI data after loading
  displayMsiData(data, fileName) {
    this.currentFileName = fileName;
    this.tablesData = data.tables;

    // Display files
    this.displayFilesList(data.files);

    // Display tables list
    this.displayTablesList(data.tables);

    // Display summary
    this.displaySummary(data.summary);

    // Display streams
    this.displayStreams(data.streams);

    // Enable the extract button and show current file
    this.extractButton.disabled = false;
    this.currentFileDisplay.textContent = `Currently loaded: ${this.currentFileName}`;
    this.currentFileDisplay.style.display = 'block';

    this.loadingIndicator.style.display = 'none';
  }

  // Display files list
  displayFilesList(filesData) {
    this.filesList.innerHTML = '';

    if (filesData.length === 0) {
      this.filesList.innerHTML = '<tr><td colspan="5">No files found</td></tr>';
      return;
    }

    for (const file of filesData) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${file.name}</td>
        <td>${file.directory}</td>
        <td>${file.size}</td>
        <td>${file.component}</td>
        <td>${file.version}</td>
      `;
      this.filesList.appendChild(row);
    }
  }

  // Display tables list
  displayTablesList(tables) {
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

  // Display summary information
  displaySummary(summaryData) {
    this.summaryContent.innerHTML = '';

    if (Object.keys(summaryData).length === 0) {
      this.summaryContent.innerHTML = '<p>No summary information available</p>';
      return;
    }

    const table = document.createElement('table');

    for (const [key, value] of Object.entries(summaryData)) {
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

  // Display streams
  displayStreams(streams) {
    this.streamsContent.innerHTML = '';

    if (streams.length === 0) {
      this.streamsContent.innerHTML = '<p>No streams available</p>';
      return;
    }

    const table = document.createElement('table');
    const headerRow = document.createElement('tr');
    headerRow.innerHTML = '<th>Name</th>';
    table.appendChild(headerRow);

    for (const stream of streams) {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${stream}</td>`;
      table.appendChild(row);
    }

    this.streamsContent.appendChild(table);
  }

  // Display table data
  displayTableData(data) {
    // Display table columns
    this.tableHeader.innerHTML = '';
    const headerRow = document.createElement('tr');

    for (const column of data.columns) {
      const th = document.createElement('th');
      th.textContent = column;
      headerRow.appendChild(th);
    }

    this.tableHeader.appendChild(headerRow);

    // Display table rows
    this.tableContent.innerHTML = '';

    if (data.rows.length === 0) {
      const emptyRow = document.createElement('tr');
      emptyRow.innerHTML = `<td colspan="${data.columns.length}">No data</td>`;
      this.tableContent.appendChild(emptyRow);
      return;
    }

    for (const rowData of data.rows) {
      const row = document.createElement('tr');

      // Iterate through columns to maintain the correct order
      for (const column of data.columns) {
        const td = document.createElement('td');
        const value = rowData[column];
        td.textContent = value !== null && value !== undefined ? String(value) : '';
        row.appendChild(td);
      }

      this.tableContent.appendChild(row);
    }

    this.loadingIndicator.style.display = 'none';
  }

  // Create ZIP from extracted files
  createZipFromExtractedFiles(files, baseFileName) {
    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Creating ZIP archive...';

    try {
      // Make sure JSZip is loaded
      if (typeof JSZip === 'undefined') {
        throw new Error('JSZip failed to load.');
      }

      const zip = new JSZip();

      // Add each file to the ZIP
      for (const file of files) {
        zip.file(file.path, file.data);
      }

      // Generate ZIP blob
      zip.generateAsync({ type: 'blob' }).then((zipBlob) => {
        // Create filename
        const zipFileName = `${baseFileName}_extracted.zip`;

        // Trigger download
        const url = URL.createObjectURL(zipBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = zipFileName;
        document.body.appendChild(a);
        a.click();

        // Clean up immediately
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.loadingIndicator.style.display = 'none';
      }).catch((error) => {
        this.loadingIndicator.textContent = `Error creating ZIP: ${error.message}`;
        console.error('Error creating ZIP:', error);
      });
    } catch (error) {
      this.loadingIndicator.textContent = `Error creating ZIP: ${error.message}`;
      console.error('Error creating ZIP:', error);
    }
  }

  // Load MSI file from ArrayBuffer (used for file input, example, and URL)
  async loadMsiFileFromArrayBuffer(arrayBuffer, fileName = 'uploaded.msi') {
    if (!this.isWorkerReady) {
      this.loadingIndicator.style.display = 'block';
      this.loadingIndicator.textContent = 'Waiting for worker to initialize...';
      // Wait for worker to be ready with exponential backoff
      if (this._loadRetries < this.WORKER_INIT_MAX_RETRIES) {
        this._loadRetries++;
        const delay = Math.min(
          this.WORKER_INIT_BASE_DELAY * Math.pow(this.WORKER_INIT_BACKOFF_FACTOR, this._loadRetries - 1),
          this.WORKER_INIT_MAX_DELAY
        );
        // Clear any existing timeout to prevent memory buildup
        if (this._loadRetryTimeout) {
          clearTimeout(this._loadRetryTimeout);
        }
        this._loadRetryTimeout = setTimeout(() => {
          this._loadRetryTimeout = null;
          this.loadMsiFileFromArrayBuffer(arrayBuffer, fileName);
        }, delay);
      } else {
        this.loadingIndicator.classList.add('error');
        this.loadingIndicator.textContent = 'Worker initialization timeout. Please refresh the page.';
        this._loadRetries = 0;
        this._loadRetryTimeout = null;
      }
      return;
    }

    // Reset retry counter and timeout on success
    this._loadRetries = 0;
    if (this._loadRetryTimeout) {
      clearTimeout(this._loadRetryTimeout);
      this._loadRetryTimeout = null;
    }

    // Send the file to the worker for processing
    this.worker.postMessage({
      type: 'load-msi',
      data: {
        arrayBuffer: arrayBuffer,
        fileName: fileName
      }
    });
  }

  // Handle file selection
  async handleFileSelect(event) {
    if (!this.fileInput.files || this.fileInput.files.length === 0) return;

    const file = this.fileInput.files[0];
    const arrayBuffer = await file.arrayBuffer();
    await this.loadMsiFileFromArrayBuffer(arrayBuffer, file.name);
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

  // Load table data when a table is selected
  loadTableData() {
    const selectedTable = this.tableSelector.value;
    if (!selectedTable || !this.isWorkerReady) return;

    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Loading table data...';

    // Request table data from worker
    this.worker.postMessage({
      type: 'load-table',
      data: {
        tableName: selectedTable
      }
    });
  }

  // Extract files and create a ZIP for download
  extractFiles() {
    if (!this.isWorkerReady || !this.currentFileName) return;

    this.loadingIndicator.style.display = 'block';
    this.loadingIndicator.textContent = 'Starting extraction...';

    // Request file extraction from worker
    this.worker.postMessage({
      type: 'extract-files',
      data: {
        fileName: this.currentFileName
      }
    });
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
