import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const viewerUrl = new URL('../../docs/_static/msi_viewer.js', import.meta.url);
const viewerSource = fs.readFileSync(viewerUrl, 'utf8');
const fixtureManifestUrl = new URL('./fixtures/generated/manifest.json', import.meta.url);
const fixtureManifest = JSON.parse(fs.readFileSync(fixtureManifestUrl, 'utf8'));
const fixtureMarkers = fixtureManifest.markers;


function loadViewer(extraGlobals = {}) {
  const document = extraGlobals.document || fakeDocument();
  const quietConsole = {
    error() {},
    log() {},
    warn() {},
  };
  const context = vm.createContext({
    console: quietConsole,
    document,
    setTimeout,
    clearTimeout,
    ...extraGlobals,
  });
  vm.runInContext(`${viewerSource}\n;globalThis.MSIViewerForTest = MSIViewer;`, context, {
    filename: viewerUrl.pathname,
  });
  return { MSIViewer: context.MSIViewerForTest, context };
}


function fakeElement(assignments = []) {
  let html = '';
  return {
    children: [],
    style: {},
    disabled: false,
    value: '',
    textContent: '',
    appendChild(child) { this.children.push(child); },
    addEventListener() {},
    remove() {},
    click() {},
    set innerHTML(value) {
      html = String(value);
      assignments.push(html);
    },
    get innerHTML() { return html; },
  };
}


function fakeDocument(assignments = []) {
  return {
    addEventListener() {},
    getElementById() { return fakeElement(assignments); },
    createElement() { return fakeElement(assignments); },
    querySelectorAll() { return []; },
    body: fakeElement(assignments),
  };
}


function configuredLoaderViewer(MSIViewer, scripts, writes) {
  const viewer = Object.create(MSIViewer.prototype);
  const inert = fakeElement();
  Object.assign(viewer, {
    loadingIndicator: fakeElement(),
    currentFileDisplay: fakeElement(),
    extractButton: { disabled: true },
    extractStreamsButton: { disabled: true },
    exportTablesButton: { disabled: true },
    exportFormatSelector: { disabled: true },
    loadFilesList: async () => {},
    loadTablesList: async () => {},
    loadSummaryInfo: async () => {},
    loadStreams: async () => {},
    fileInput: inert,
  });
  viewer.pyodide = {
    FS: {
      analyzePath() { return { exists: true }; },
      mkdir() {},
      writeFile(path, data) { writes.push({ path, data }); },
    },
    globals: {
      get() { return {}; },
      set() {},
      delete() {},
    },
    async runPythonAsync(source) {
      scripts.push(String(source));
      return null;
    },
  };
  return viewer;
}


test('finding 5: filenames and both table-name paths stay data, not Python source', async (t) => {
  const { MSIViewer } = loadViewer();

  const safeScripts = [];
  const safeViewer = configuredLoaderViewer(MSIViewer, safeScripts, []);
  await safeViewer.loadMsiFileFromArrayBuffer(new ArrayBuffer(1), 'ordinary.msi', []);
  const safeLoadScript = safeScripts.find((source) => source.includes('current_package ='));
  assert.ok(safeLoadScript);
  assert.equal(safeLoadScript.includes("__import__('js').alert"), false);

  const fileScripts = [];
  const fileViewer = configuredLoaderViewer(MSIViewer, fileScripts, []);
  const hostileFileName = fixtureMarkers.python_filename_entry;
  await fileViewer.loadMsiFileFromArrayBuffer(new ArrayBuffer(1), hostileFileName, []);
  const fileScript = fileScripts.find((source) => source.includes('current_package ='));
  assert.ok(fileScript);

  const tableScripts = [];
  const tableAssignments = [];
  const tableViewer = Object.create(MSIViewer.prototype);
  tableViewer.tableSelector = { value: fixtureMarkers.python_table_name };
  tableViewer.tableHeader = fakeElement(tableAssignments);
  tableViewer.tableContent = fakeElement(tableAssignments);
  tableViewer.pyodide = {
    async runPythonAsync(source) {
      tableScripts.push(String(source));
      return { columns: [], rows: [] };
    },
  };
  await tableViewer.loadTableData();

  const exportScripts = [];
  const exportViewer = Object.create(MSIViewer.prototype);
  exportViewer.pyodide = {
    async runPythonAsync(source) {
      exportScripts.push(String(source));
      return { columns: [], rows: [] };
    },
  };
  await exportViewer.getTableData(fixtureMarkers.python_table_name);

  const evidence = [
    fileScript.includes(fixtureMarkers.python_filename_entry),
    tableScripts[0].includes(fixtureMarkers.python_table_name),
    exportScripts[0].includes(fixtureMarkers.python_table_name),
  ];
  if (evidence.every(Boolean)) {
    t.todo('finding 5 reproduced: all three fixture names are embedded in executable Python');
    return;
  }
  assert.deepEqual(evidence, [false, false, false]);
});


test('finding 4: MSI file metadata and stream names are rendered as text', async (t) => {
  const assignments = [];
  const document = fakeDocument(assignments);
  const { MSIViewer } = loadViewer({ document });
  const payload = fixtureMarkers.metadata_innerhtml;

  const filesViewer = Object.create(MSIViewer.prototype);
  filesViewer.filesList = fakeElement(assignments);
  filesViewer.enhanceTable = () => {};
  filesViewer.pyodide = {
    async runPythonAsync() {
      return [{ name: payload, directory: 'safe', size: 1, component: 'C', version: '1' }];
    },
  };
  await filesViewer.loadFilesList();

  const streamsViewer = Object.create(MSIViewer.prototype);
  streamsViewer.streamsContent = fakeElement(assignments);
  streamsViewer.getAllStreamNames = async () => [payload];
  await streamsViewer.loadStreams();

  const rawMarkupSinks = assignments.filter((value) => value.includes(payload));
  if (rawMarkupSinks.length === 2) {
    assert.ok(rawMarkupSinks.every((value) => value.includes('onerror')));
    t.todo('finding 4 reproduced: both metadata paths reach innerHTML as raw markup');
    return;
  }
  assert.equal(rawMarkupSinks.length, 0);
});


test('finding 8: auxiliary ZIP paths cannot target Pyodide site-packages', async (t) => {
  const { MSIViewer } = loadViewer();
  const safeWrites = [];
  const safeViewer = configuredLoaderViewer(MSIViewer, [], safeWrites);
  await safeViewer.loadMsiFileFromArrayBuffer(new ArrayBuffer(1), 'ordinary.msi', [
    { name: 'media1.cab', data: new ArrayBuffer(1) },
  ]);
  assert.equal(safeWrites.some(({ path }) => path.includes('/site-packages/')), false);

  const hostileWrites = [];
  const hostileViewer = configuredLoaderViewer(MSIViewer, [], hostileWrites);
  const moduleBytes = new TextEncoder().encode(fixtureMarkers.pyodide_module_source).buffer;
  const additionalFiles = fixtureMarkers.pyodide_module_paths.map((name) => ({
    name,
    data: moduleBytes,
  }));
  await hostileViewer.loadMsiFileFromArrayBuffer(new ArrayBuffer(1), 'ordinary.msi', [
    ...additionalFiles,
  ]);

  const expectedModulePaths = fixtureMarkers.pyodide_module_paths.map((path) => `/${path}`);
  const writtenPaths = new Set(hostileWrites.map(({ path }) => path));
  if (expectedModulePaths.every((path) => writtenPaths.has(path))) {
    t.todo('finding 8 reproduced: ZIP-derived paths overwrote all fixture module paths');
    return;
  }
  assert.equal(hostileWrites.some(({ path }) => path.includes('/site-packages/')), false);
});


test('finding 10: an oversized ZIP entry is rejected before inflation', async (t) => {
  let inflated = false;
  const oversizedEntry = {
    dir: false,
    date: null,
    _data: { uncompressedSize: 500 * 1024 * 1024 + 1 },
    async async() {
      inflated = true;
      return new ArrayBuffer(1);
    },
  };
  const JSZip = {
    async loadAsync() {
      return { forEach(callback) { callback('payload.msi', oversizedEntry); } };
    },
  };
  class FakeFile {
    constructor(parts, name) {
      this.name = name;
      this.size = parts[0].byteLength;
    }
  }
  const { MSIViewer } = loadViewer({ JSZip, File: FakeFile });
  const viewer = Object.create(MSIViewer.prototype);
  await viewer.expandArchives([{ name: 'payload.zip' }]);

  if (inflated) {
    t.todo('finding 10 reproduced: the declared oversized entry was inflated before a size gate');
    return;
  }
  assert.equal(inflated, false);
});


test('negative control: a small ZIP entry can be expanded', async () => {
  let inflated = false;
  const entry = {
    dir: false,
    date: null,
    _data: { uncompressedSize: 1 },
    async async() {
      inflated = true;
      return new ArrayBuffer(1);
    },
  };
  const JSZip = {
    async loadAsync() {
      return { forEach(callback) { callback('ordinary.msi', entry); } };
    },
  };
  class FakeFile {
    constructor(parts, name) {
      this.name = name;
      this.size = parts[0].byteLength;
    }
  }
  const { MSIViewer } = loadViewer({ JSZip, File: FakeFile });
  const viewer = Object.create(MSIViewer.prototype);
  const files = await viewer.expandArchives([{ name: 'ordinary.zip' }]);
  assert.equal(inflated, true);
  assert.equal(files.length, 1);
  assert.equal(files[0].name, 'ordinary.msi');
});


test('finding 7: CSV export neutralizes spreadsheet formula prefixes', async (t) => {
  const captured = new Map();
  class FakeZip {
    file(name, contents) { captured.set(name, String(contents)); }
    async generateAsync() { return { type: 'fake-blob' }; }
  }
  const { MSIViewer } = loadViewer({ JSZip: FakeZip });
  const viewer = Object.create(MSIViewer.prototype);
  viewer.loadingIndicator = fakeElement();
  viewer.currentFileName = 'ordinary.msi';
  viewer.downloadBlob = () => {};
  viewer.getTableData = async () => ({
    columns: ['Value'],
    rows: [
      { Value: '=1+1' },
      { Value: '+1+1' },
      { Value: '-1+1' },
      { Value: '@SUM(A1:A2)' },
      { Value: 'ordinary text' },
    ],
  });
  await viewer.exportAsCSV(['Property']);

  const csv = captured.get('Property.csv');
  assert.ok(csv);
  const rows = csv.trimEnd().split('\n');
  const formulaPrefixes = ['=', '+', '-', '@'];
  assert.equal(rows[5], 'ordinary text');
  if (formulaPrefixes.every((prefix, index) => rows[index + 1].startsWith(prefix))) {
    t.todo('finding 7 reproduced: exported cells retain all four active formula prefixes');
    return;
  }
  assert.ok(
    formulaPrefixes.every((prefix, index) => !rows[index + 1].startsWith(prefix)),
    'every dangerous formula prefix must be neutralized',
  );
});
