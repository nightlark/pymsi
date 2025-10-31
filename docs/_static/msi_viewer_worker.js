// MSI Viewer Web Worker - Handles Pyodide operations in a separate thread
//
// This web worker runs Pyodide (Python runtime) in a background thread to prevent
// blocking the main UI thread. This is especially important for:
// - Large MSI files that take time to parse
// - MSI files using LZX compression which requires significant CPU
// - File extraction operations that can take several seconds
//
// The worker communicates with the main thread via postMessage, sending:
// - Progress updates during long operations
// - Error messages if something goes wrong
// - Processed data (files, tables, summary info) back to the main thread
//
// This architecture ensures the browser UI remains responsive and prevents
// "page unresponsive" warnings during MSI processing.

let pyodide = null;
let pymsi = null;
let currentPackage = null;
let currentMsi = null;

// Send progress updates to the main thread
function sendProgress(message, isError = false) {
  self.postMessage({
    type: 'progress',
    message: message,
    isError: isError
  });
}

// Initialize Pyodide
async function initPyodide() {
  try {
    sendProgress('Loading Pyodide...');
    
    // Import Pyodide from CDN
    importScripts('https://cdn.jsdelivr.net/pyodide/v0.23.4/full/pyodide.js');
    
    pyodide = await loadPyodide();
    if (!pyodide) {
      throw new Error('loadPyodide() failed.');
    }

    sendProgress('Loading pymsi...');

    // Install pymsi using micropip
    await pyodide.loadPackagesFromImports('import micropip');
    const micropip = pyodide.pyimport('micropip');
    await micropip.install('python-msi');

    // Import required modules
    await pyodide.runPythonAsync(`
      import pymsi
      import json
      import io
      import zipfile
      import shutil
      import os
      from pathlib import Path
      from pyodide.ffi import to_js
    `);

    pymsi = pyodide.pyimport('pymsi');
    
    sendProgress('Ready', false);
    
    self.postMessage({
      type: 'initialized',
      success: true
    });
  } catch (error) {
    sendProgress(`Error loading Pyodide or pymsi: ${error.message}`, true);
    self.postMessage({
      type: 'initialized',
      success: false,
      error: error.message
    });
  }
}

// Load MSI file from ArrayBuffer
async function loadMsiFile(arrayBuffer, fileName) {
  try {
    sendProgress('Reading MSI file...');

    // Read the file as a Uint8Array
    const msiBinaryData = new Uint8Array(arrayBuffer);

    // Write the file to Pyodide's virtual file system
    pyodide.FS.writeFile('/uploaded.msi', msiBinaryData);

    sendProgress('Parsing MSI structure...');

    // Create Package and Msi objects using the file path
    await pyodide.runPythonAsync(`
      from pathlib import Path
      current_package = pymsi.Package(Path('/uploaded.msi'))
      current_msi = pymsi.Msi(current_package, True)
    `);

    currentPackage = await pyodide.globals.get('current_package');
    currentMsi = await pyodide.globals.get('current_msi');

    sendProgress('Loading file information...');

    // Load all the data
    const filesData = await getFilesData();
    const tablesData = await getTablesData();
    const summaryData = await getSummaryData();
    const streamsData = await getStreamsData();

    sendProgress('MSI file loaded successfully');

    self.postMessage({
      type: 'msi-loaded',
      success: true,
      fileName: fileName,
      data: {
        files: filesData,
        tables: tablesData,
        summary: summaryData,
        streams: streamsData
      }
    });
  } catch (error) {
    sendProgress(`Error processing MSI file: ${error.message}`, true);
    self.postMessage({
      type: 'msi-loaded',
      success: false,
      error: error.message
    });
  }
}

// Get files data
async function getFilesData() {
  const filesData = await pyodide.runPythonAsync(`
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
  
  // Convert to plain JS array
  const result = [];
  for (const file of filesData) {
    result.push({
      name: file.get("name") || '',
      directory: file.get("directory") || '',
      size: file.get("size") || '',
      component: file.get("component") || '',
      version: file.get("version") || ''
    });
  }
  return result;
}

// Get tables data
async function getTablesData() {
  const tables = await pyodide.runPythonAsync(`
    tables = []
    for k in current_package.ole.root.kids:
      name, is_table = pymsi.streamname.decode_unicode(k.name)
      if is_table:
        tables.append(name)
    to_js(tables)
  `);
  
  // Convert to plain JS array
  const result = [];
  for (const table of tables) {
    result.push(table);
  }
  return result;
}

// Get summary data
async function getSummaryData() {
  const summaryData = await pyodide.runPythonAsync(`
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
  
  // Convert to plain JS object
  const result = {};
  for (const [key, value] of summaryData) {
    result[key] = value !== null ? String(value) : '';
  }
  return result;
}

// Get streams data
async function getStreamsData() {
  const streamsData = await pyodide.runPythonAsync(`
    streams = []
    for k in current_package.ole.root.kids:
      name, is_table = pymsi.streamname.decode_unicode(k.name)
      if not is_table:
        streams.append(name)
    to_js(streams)
  `);
  
  // Convert to plain JS array
  const result = [];
  for (const stream of streamsData) {
    result.push(stream);
  }
  return result;
}

// Load table data for a specific table
async function loadTableData(tableName) {
  try {
    const tableData = await pyodide.runPythonAsync(`
      result = {'columns': [], 'rows': []}
      try:
        table = current_package.get('${tableName}')
        result['columns'] = [column.name for column in table.columns]
        result['rows'] = [row for row in table.rows]
      except Exception as e:
        print(f"Error getting table data: {e}")
      to_js(result)
    `);

    // Convert columns
    const columns = [];
    for (const column of tableData.get("columns")) {
      columns.push(column);
    }

    // Convert rows
    const rows = [];
    for (const rowData of tableData.get("rows")) {
      const row = {};
      for (const column of columns) {
        const value = rowData.get(column);
        row[column] = (value !== null && value !== undefined) ? String(value) : '';
      }
      rows.push(row);
    }

    self.postMessage({
      type: 'table-data',
      success: true,
      tableName: tableName,
      data: {
        columns: columns,
        rows: rows
      }
    });
  } catch (error) {
    self.postMessage({
      type: 'table-data',
      success: false,
      tableName: tableName,
      error: error.message
    });
  }
}

// Extract files and create a ZIP
async function extractFiles(fileName) {
  try {
    sendProgress('Extracting files...');

    // Import and use the extract_root function from __main__.py
    await pyodide.runPythonAsync(`
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

    sendProgress('Collecting extracted files...');

    // Get list of all extracted files
    const fileList = await pyodide.runPythonAsync(`
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
      sendProgress('No files extracted', true);
      self.postMessage({
        type: 'extract-complete',
        success: false,
        error: 'No files extracted'
      });
      return;
    }

    sendProgress('Reading extracted files...');

    // Read all files and send them back to the main thread
    const extractedFiles = [];
    for (const filePath of fileList) {
      const fileData = pyodide.FS.readFile(`/tmp/extracted/${filePath}`);
      extractedFiles.push({
        path: filePath,
        data: fileData
      });
    }

    sendProgress('Files extracted successfully');

    self.postMessage({
      type: 'extract-complete',
      success: true,
      files: extractedFiles,
      baseFileName: fileName.replace(/\.msi$/i, '')
    });
  } catch (error) {
    sendProgress(`Error extracting files: ${error.message}`, true);
    self.postMessage({
      type: 'extract-complete',
      success: false,
      error: error.message
    });
  }
}

// Handle messages from the main thread
self.addEventListener('message', async (event) => {
  const { type, data } = event.data;

  switch (type) {
    case 'init':
      await initPyodide();
      break;

    case 'load-msi':
      await loadMsiFile(data.arrayBuffer, data.fileName);
      break;

    case 'load-table':
      await loadTableData(data.tableName);
      break;

    case 'extract-files':
      await extractFiles(data.fileName);
      break;

    default:
      console.warn('Unknown message type:', type);
  }
});
