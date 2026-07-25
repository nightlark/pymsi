(() => {
    "use strict";

    const INITIAL_PREVIEW_LIMIT = 64 * 1024;
    const FIRST_EXPANDED_PREVIEW_LIMIT = 256 * 1024;
    const DOWNLOAD_URL_REVOKE_DELAY_MS = 1000;
    let pythonNameCounter = 0;
    let activeRequestToken = 0;
    let previousFocus = null;
    let modalState = null;

    function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) {
            element.className = className;
        }
        if (text !== undefined && text !== null) {
            element.textContent = String(text);
        }
        return element;
    }

    function nextPythonName(prefix) {
        pythonNameCounter += 1;
        return `_pymsi_${prefix}_${pythonNameCounter}`;
    }

    function makeInspectButton(
        request,
        label = "Inspect",
        disabledReason = null,
    ) {
        const button = makeElement("button", "binary-reference", label);
        button.type = "button";
        if (request) {
            button.dataset.binaryRequest = JSON.stringify(request);
        }
        if (disabledReason) {
            button.disabled = true;
            button.title = disabledReason;
            button.setAttribute("aria-label", `${label}: ${disabledReason}`);
        } else {
            button.title = "Open bytes in the hex/ASCII viewer";
        }
        return button;
    }

    function installStyles() {
        if (document.getElementById("pymsi-binary-viewer-styles")) {
            return;
        }
        const style = makeElement("style");
        style.id = "pymsi-binary-viewer-styles";
        style.textContent = `
            .binary-reference {
                margin-left: .45rem;
                padding: .2rem .55rem;
                border: 1px solid var(--msi-accent-border, #9bc4f5);
                border-radius: 4px;
                background: var(--msi-surface, #f6f7fb);
                color: var(--msi-accent, #06c);
                cursor: pointer;
                font: inherit;
                font-size: .85rem;
                line-height: 1.3;
                white-space: nowrap;
            }
            .binary-reference:hover,
            .binary-reference:focus-visible {
                border-color: var(--msi-accent, #06c);
                background: var(--msi-overlay, #eef2f7);
                outline: none;
            }
            .binary-reference:disabled {
                border-color: var(--msi-border, #d5d8de);
                background: var(--msi-disabled-surface, #eef1f5);
                color: var(--msi-muted, #4b5563);
                cursor: not-allowed;
                opacity: .75;
            }
            .binary-cell { min-width: 10rem; }
            .binary-value-marker { font-family: var(--font-stack--monospace, ui-monospace, SFMono-Regular, Consolas, monospace); }
            .binary-viewer-overlay {
                position: fixed;
                inset: 0;
                z-index: 10000;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 1rem;
                background: rgba(0, 0, 0, .62);
            }
            .binary-viewer-overlay[hidden] { display: none; }
            .binary-viewer-dialog {
                display: flex;
                flex-direction: column;
                width: min(96vw, 48rem);
                max-height: 92vh;
                overflow: hidden;
                box-sizing: border-box;
                border: 1px solid var(--msi-border, #777);
                border-radius: 8px;
                background: var(--msi-bg, #fff);
                color: var(--msi-foreground, #111);
                box-shadow: 0 1rem 3rem rgba(0, 0, 0, .35);
            }
            .binary-viewer-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 1rem;
                padding: .85rem 1rem;
                border-bottom: 1px solid var(--msi-border, #d0d0d0);
            }
            .binary-viewer-header h2 {
                margin: 0;
                font-size: 1.1rem;
                overflow-wrap: anywhere;
            }
            .binary-viewer-close {
                flex: 0 0 auto;
                border: 0;
                background: transparent;
                color: inherit;
                cursor: pointer;
                font-size: 1.5rem;
                line-height: 1;
            }
            .binary-viewer-meta {
                padding: .65rem 1rem;
                border-bottom: 1px solid var(--msi-border, #d0d0d0);
                font-family: var(--font-stack--monospace, ui-monospace, SFMono-Regular, Consolas, monospace);
                font-size: .85rem;
                overflow-wrap: anywhere;
            }
            .binary-viewer-controls {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: .5rem;
                padding: .55rem 1.25rem;
                border-bottom: 1px solid var(--msi-border, #d0d0d0);
                background: var(--msi-bg, #fff);
            }
            .binary-viewer-controls[hidden] { display: none; }
            .binary-viewer-control { margin-left: 0; }
            .binary-viewer-status {
                margin-left: auto;
                color: var(--msi-muted, #4b5563);
                font-size: .85rem;
                overflow-wrap: anywhere;
            }
            .binary-viewer-body {
                margin: 0;
                padding: 1rem 1.25rem;
                overflow: auto;
                background: var(--msi-surface, #f4f4f4);
                color: var(--msi-foreground, #111);
                font-family: var(--font-stack--monospace, ui-monospace, SFMono-Regular, Consolas, monospace);
                font-size: .82rem;
                line-height: 1.35;
                tab-size: 4;
                white-space: pre;
            }
            .binary-viewer-error {
                color: var(--msi-foreground, #111);
                white-space: pre-wrap;
            }
            body.binary-viewer-open { overflow: hidden; }
            #analysis-tab .analysis-data-reference {
                grid-template-columns: minmax(7rem, 11rem) minmax(0, 1fr) auto;
                align-items: center;
            }
            #analysis-tab .analysis-data-reference .binary-reference {
                justify-self: start;
            }
            @media (max-width: 700px) {
                .binary-viewer-overlay { padding: .35rem; }
                .binary-viewer-dialog { width: 100%; max-height: 96vh; }
                .binary-viewer-controls { padding: .5rem .65rem; }
                .binary-viewer-status {
                    flex-basis: 100%;
                    margin-left: 0;
                }
                .binary-viewer-body { padding: .65rem; font-size: .76rem; }
                #analysis-tab .analysis-data-reference { grid-template-columns: 1fr; }
                #analysis-tab .analysis-data-reference .binary-reference {
                    margin-left: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function modalHost() {
        return document.getElementById("msi-viewer-app") || document.body;
    }

    function formatByteSize(value) {
        const bytes = Math.max(0, Number(value) || 0);
        const units = ["bytes", "KiB", "MiB", "GiB"];
        let amount = bytes;
        let unit = 0;
        while (amount >= 1024 && unit < units.length - 1) {
            amount /= 1024;
            unit += 1;
        }
        const digits = unit === 0 || amount >= 10 ? 0 : 1;
        return `${amount.toFixed(digits)} ${units[unit]}`;
    }

    function safeDownloadName(value, fallback = "payload.bin") {
        let name = String(value || "");
        if (name.includes("|")) {
            const [shortName, longName] = name.split("|", 2);
            name = longName || shortName;
        }
        name = name.replace(/\\/g, "/").split("/").pop() || "";
        name = name
            .replace(/[\u0000-\u001f\u007f<>:"/\\|?*]+/g, "_")
            .replace(/[. ]+$/g, "")
            .trim();
        if (!name || name === "." || name === "..") {
            return fallback;
        }
        return name;
    }

    function suggestedDownloadName(state = modalState) {
        if (!state) {
            return "payload.bin";
        }
        const { request, payload, viewer } = state;
        let candidate = payload?.download_name || request?.download_name || null;
        let fallback = "payload.bin";
        if (request?.kind === "file") {
            const record = viewer?._pymsiBinaryFileRecords?.get(
                String(request.file_id),
            );
            candidate = candidate || request.display_name || record?.name || request.file_id;
            fallback = `${request.file_id || "file"}.bin`;
        } else if (request?.kind === "stream") {
            candidate = candidate || request.stream_name;
            fallback = "stream.bin";
        } else if (request?.kind === "table") {
            const keys = Array.from(
                request.primary_keys || [],
                (value) => String(value),
            );
            candidate = [request.table || "table", ...keys].join(".");
            fallback = `${request.table || "payload"}.bin`;
        }
        return safeDownloadName(candidate, safeDownloadName(fallback));
    }

    function nextPreviewLimit(state = modalState) {
        if (!state?.payload) {
            return null;
        }
        const total = Number(state.payload.size);
        const shown = Number(state.payload.preview_size);
        if (!Number.isFinite(total) || !Number.isFinite(shown) || shown >= total) {
            return null;
        }
        const expanded =
            shown < FIRST_EXPANDED_PREVIEW_LIMIT
                ? FIRST_EXPANDED_PREVIEW_LIMIT
                : shown * 2;
        return Math.min(expanded, total);
    }

    function updateModalControls() {
        const controls = document.getElementById("pymsi-binary-controls");
        const showMore = document.getElementById("pymsi-binary-show-more");
        const download = document.getElementById("pymsi-binary-download");
        const status = document.getElementById("pymsi-binary-status");
        if (!controls || !showMore || !download || !status) {
            return;
        }

        const state = modalState;
        const hasPayload = Boolean(state?.payload);
        controls.hidden = !hasPayload;
        if (!hasPayload) {
            showMore.hidden = true;
            showMore.disabled = true;
            download.disabled = true;
            status.textContent = "";
            return;
        }

        const busy = Boolean(state.loadingPreview || state.downloading);
        const nextLimit = nextPreviewLimit(state);
        showMore.hidden = nextLimit === null;
        showMore.disabled = busy || nextLimit === null;
        if (nextLimit !== null) {
            showMore.textContent =
                nextLimit >= Number(state.payload.size)
                    ? "Show all"
                    : `Show ${formatByteSize(nextLimit)}`;
            showMore.title = `Render up to ${formatByteSize(nextLimit)} in the hex viewer`;
        }

        const downloadName = suggestedDownloadName(state);
        download.disabled = busy;
        download.textContent = state.downloading ? "Preparing…" : "Download";
        download.title = `Download the complete payload as ${downloadName}`;
        download.setAttribute("aria-label", `Download ${downloadName}`);

        if (state.status) {
            status.textContent = state.status;
        } else {
            status.textContent = "";
        }
    }

    function closeModal({ restoreFocus = true } = {}) {
        activeRequestToken += 1;
        const overlay = document.getElementById("pymsi-binary-viewer");
        if (overlay) {
            overlay.hidden = true;
        }
        document.body.classList.remove("binary-viewer-open");
        if (
            restoreFocus &&
            previousFocus instanceof HTMLElement &&
            previousFocus.isConnected
        ) {
            previousFocus.focus();
        }
        previousFocus = null;
        modalState = null;
        updateModalControls();
    }

    function ensureModal() {
        let overlay = document.getElementById("pymsi-binary-viewer");
        if (overlay) {
            return overlay;
        }
        overlay = makeElement("div", "binary-viewer-overlay");
        overlay.id = "pymsi-binary-viewer";
        overlay.hidden = true;
        overlay.setAttribute("role", "presentation");

        const dialog = makeElement("section", "binary-viewer-dialog");
        dialog.setAttribute("role", "dialog");
        dialog.setAttribute("aria-modal", "true");
        dialog.setAttribute("aria-labelledby", "pymsi-binary-title");
        dialog.setAttribute("aria-describedby", "pymsi-binary-meta");

        const header = makeElement("header", "binary-viewer-header");
        const title = makeElement("h2", "", "Binary data");
        title.id = "pymsi-binary-title";
        const close = makeElement("button", "binary-viewer-close", "×");
        close.type = "button";
        close.setAttribute("aria-label", "Close binary viewer");
        header.append(title, close);

        const meta = makeElement("div", "binary-viewer-meta");
        meta.id = "pymsi-binary-meta";
        const controls = makeElement("div", "binary-viewer-controls");
        controls.id = "pymsi-binary-controls";
        controls.hidden = true;
        const showMore = makeElement(
            "button",
            "binary-reference binary-viewer-control",
            "Show more",
        );
        showMore.id = "pymsi-binary-show-more";
        showMore.type = "button";
        const download = makeElement(
            "button",
            "binary-reference binary-viewer-control",
            "Download",
        );
        download.id = "pymsi-binary-download";
        download.type = "button";
        const status = makeElement("span", "binary-viewer-status");
        status.id = "pymsi-binary-status";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        controls.append(showMore, download, status);
        const body = makeElement("pre", "binary-viewer-body");
        body.id = "pymsi-binary-body";

        dialog.append(header, meta, controls, body);
        overlay.appendChild(dialog);
        modalHost().appendChild(overlay);

        close.addEventListener("click", () => closeModal());
        showMore.addEventListener("click", () => {
            void showMoreCurrentPayload();
        });
        download.addEventListener("click", () => {
            void downloadCurrentPayload();
        });
        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) {
                closeModal();
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !overlay.hidden) {
                closeModal();
            }
        });
        return overlay;
    }

    function showModal(titleText, metaText, bodyText, isError = false) {
        const overlay = ensureModal();
        const wasHidden = overlay.hidden;
        if (wasHidden) {
            previousFocus = document.activeElement;
        }
        const title = document.getElementById("pymsi-binary-title");
        const meta = document.getElementById("pymsi-binary-meta");
        const body = document.getElementById("pymsi-binary-body");
        title.textContent = titleText;
        meta.textContent = metaText || "";
        body.textContent = bodyText || "";
        body.classList.toggle("binary-viewer-error", isError);
        overlay.hidden = false;
        document.body.classList.add("binary-viewer-open");
        modalHost().classList.add("binary-viewer-open");
        updateModalControls();
        if (wasHidden) {
            overlay.querySelector(".binary-viewer-close").focus();
        }
    }

    function decodeBase64(value) {
        const binary = atob(value || "");
        const result = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            result[index] = binary.charCodeAt(index);
        }
        return result;
    }

    function coerceUint8Array(value) {
        let converted = value;
        try {
            if (value && typeof value.toJs === "function") {
                converted = value.toJs();
            }
            if (converted instanceof Uint8Array) {
                return new Uint8Array(converted);
            }
            if (ArrayBuffer.isView(converted)) {
                return new Uint8Array(
                    converted.buffer.slice(
                        converted.byteOffset,
                        converted.byteOffset + converted.byteLength,
                    ),
                );
            }
            if (converted instanceof ArrayBuffer) {
                return new Uint8Array(converted.slice(0));
            }
            if (Array.isArray(converted)) {
                return new Uint8Array(converted);
            }
            throw new Error("Pyodide returned an unsupported binary data type");
        } finally {
            if (
                converted !== value &&
                converted &&
                typeof converted.destroy === "function"
            ) {
                converted.destroy();
            }
            if (value && typeof value.destroy === "function") {
                value.destroy();
            }
        }
    }

    function formatHex(bytes, totalSize) {
        const lines = [];
        const offsetWidth = Math.max(
            8,
            Math.max(0, Number(totalSize) - 1).toString(16).length,
        );
        for (let offset = 0; offset < bytes.length; offset += 16) {
            const chunk = bytes.subarray(
                offset,
                Math.min(offset + 16, bytes.length),
            );
            const hexGroups = [];
            for (let groupOffset = 0; groupOffset < 16; groupOffset += 8) {
                const group = chunk.subarray(groupOffset, groupOffset + 8);
                hexGroups.push(
                    Array.from(group, (byte) =>
                        byte.toString(16).padStart(2, "0"),
                    )
                        .join(" ")
                        .padEnd(23, " "),
                );
            }
            const ascii = Array.from(chunk, (byte) =>
                byte >= 0x20 && byte <= 0x7e ? String.fromCharCode(byte) : ".",
            ).join("");
            lines.push(
                `${offset.toString(16).padStart(offsetWidth, "0")}  ` +
                    `${hexGroups.join("  ")}  |${ascii.padEnd(16, " ")}|`,
            );
        }
        if (!bytes.length) {
            lines.push("(empty stream)");
        }
        if (totalSize > bytes.length) {
            lines.push("");
            lines.push(
                `… ${(totalSize - bytes.length).toLocaleString()} additional byte(s) not rendered`,
            );
        }
        return lines.join("\n");
    }

    function requestLabel(request) {
        if (request.kind === "table") {
            return `${request.table}[${(request.primary_keys || []).join(", ")}]`;
        }
        if (request.kind === "stream") {
            return `Stream ${request.stream_name}`;
        }
        if (request.kind === "file") {
            const name = request.display_name ? ` (${request.display_name})` : "";
            return `File ${request.file_id}${name}`;
        }
        return "Binary data";
    }

    async function runBinaryRequest(
        viewer,
        request,
        { previewLimit = INITIAL_PREVIEW_LIMIT, response = "preview" } = {},
    ) {
        const requestGlobal = nextPythonName("binary_payload_request");
        const functionGlobal = nextPythonName("read_binary_payload");
        viewer.pyodide.globals.set(
            requestGlobal,
            JSON.stringify({
                ...request,
                preview_limit: previewLimit,
                response,
            }),
        );
        try {
            const result = await viewer.pyodide.runPythonAsync(`
def ${functionGlobal}(_request_json):
    import base64
    import hashlib
    import json
    from pyodide.ffi import to_js

    request = json.loads(_request_json)
    kind = request["kind"]
    download_name = request.get("download_name") or request.get("display_name")

    if kind == "table":
        table_name = request["table"]
        keys = request.get("primary_keys") or []
        data = current_package.get_datastream_bytes(table_name, *keys)
        if data is None:
            raise ValueError("Referenced Binary/OBJECT stream was not found")
        download_name = ".".join(
            str(value) for value in (table_name, *keys)
        )
    elif kind == "stream":
        data = None
        for child in current_package.ole.root.kids:
            name, is_table = pymsi.streamname.decode_unicode(child.name)
            if not is_table and name == request["stream_name"]:
                with current_package.ole.openstream(child.name) as stream:
                    data = stream.read()
                break
        if data is None:
            raise ValueError("OLE stream was not found")
        download_name = download_name or request["stream_name"]
    elif kind == "file":
        file_id = request["file_id"]
        try:
            file = current_msi.files[file_id]
        except KeyError as error:
            raise ValueError(f"File-table row {file_id!r} was not found") from error
        data = file.resolve().decompress()
        file_name = str(file.name or "")
        if "|" in file_name:
            short_name, long_name = file_name.split("|", 1)
            file_name = long_name or short_name
        download_name = file_name or download_name or str(file_id)
    else:
        raise ValueError(f"Unsupported binary request kind: {kind}")

    data = bytes(data)
    if request.get("response") == "bytes":
        return to_js(data)
    if request.get("response") != "preview":
        raise ValueError(f"Unsupported binary response: {request.get('response')}")

    limit = max(0, int(request["preview_limit"]))
    preview = data[:limit]
    return json.dumps(
        {
            "size": len(data),
            "preview_size": len(preview),
            "preview_base64": base64.b64encode(preview).decode("ascii"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "download_name": download_name,
        },
        ensure_ascii=False,
    )

${functionGlobal}(${requestGlobal})
`);
            if (response === "bytes") {
                return coerceUint8Array(result);
            }
            return JSON.parse(result);
        } finally {
            viewer.pyodide.globals.delete(requestGlobal);
            viewer.pyodide.globals.delete(functionGlobal);
        }
    }

    function payloadMeta(payload) {
        return [
            `${Number(payload.size).toLocaleString()} byte(s)`,
            `showing ${Number(payload.preview_size).toLocaleString()}`,
            `SHA-256 ${payload.sha256}`,
        ].join(" · ");
    }

    function renderPayload(state, { preserveScroll = false } = {}) {
        if (modalState !== state || !state.payload || !state.bytes) {
            return;
        }
        const body = document.getElementById("pymsi-binary-body");
        const scrollTop = preserveScroll ? body?.scrollTop || 0 : 0;
        showModal(
            state.label,
            payloadMeta(state.payload),
            formatHex(state.bytes, Number(state.payload.size)),
        );
        if (body) {
            body.scrollTop = scrollTop;
        }
        updateModalControls();
    }

    async function loadPreview(
        state,
        previewLimit,
        { preserveScroll = false } = {},
    ) {
        const token = ++activeRequestToken;
        state.loadingPreview = true;
        state.status = state.payload
            ? `Rendering up to ${formatByteSize(previewLimit)}…`
            : "";
        updateModalControls();
        try {
            const payload = await runBinaryRequest(state.viewer, state.request, {
                previewLimit,
            });
            if (token !== activeRequestToken || modalState !== state) {
                return;
            }
            if (payload.download_name && state.request.kind === "file") {
                state.request = {
                    ...state.request,
                    display_name: payload.download_name,
                };
                state.label = requestLabel(state.request);
            }
            state.payload = payload;
            state.bytes = decodeBase64(payload.preview_base64);
            state.previewLimit = previewLimit;
            state.loadingPreview = false;
            state.status = "";
            renderPayload(state, { preserveScroll });
        } catch (error) {
            if (token !== activeRequestToken || modalState !== state) {
                return;
            }
            state.loadingPreview = false;
            const message = error && error.message ? error.message : String(error);
            console.error("Could not read binary data", error);
            if (state.payload) {
                state.status = `Could not render more bytes: ${message}`;
                updateModalControls();
            } else {
                showModal(state.label, "Read failed", message, true);
            }
        }
    }

    async function openRequest(viewer, request) {
        const state = {
            viewer,
            request,
            label: requestLabel(request),
            payload: null,
            bytes: null,
            previewLimit: INITIAL_PREVIEW_LIMIT,
            loadingPreview: false,
            downloading: false,
            status: "",
        };
        modalState = state;
        showModal(state.label, "Reading bytes…", "");
        await loadPreview(state, INITIAL_PREVIEW_LIMIT);
    }

    async function showMoreCurrentPayload() {
        const state = modalState;
        if (!state || state.loadingPreview || state.downloading) {
            return;
        }
        const limit = nextPreviewLimit(state);
        if (limit === null) {
            return;
        }
        await loadPreview(state, limit, { preserveScroll: true });
    }

    function triggerDownload(bytes, filename, viewer) {
        const blob = new Blob([bytes], { type: "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
        const delay =
            Number(viewer?.DOWNLOAD_CLEANUP_DELAY_MS) ||
            DOWNLOAD_URL_REVOKE_DELAY_MS;
        setTimeout(() => {
            link.remove();
            URL.revokeObjectURL(url);
        }, delay);
    }

    async function downloadCurrentPayload() {
        const state = modalState;
        if (!state?.payload || state.loadingPreview || state.downloading) {
            return;
        }
        const filename = suggestedDownloadName(state);
        state.downloading = true;
        state.status = `Preparing ${filename}…`;
        updateModalControls();
        try {
            const bytes = await runBinaryRequest(state.viewer, state.request, {
                response: "bytes",
            });
            if (modalState !== state) {
                return;
            }
            triggerDownload(bytes, filename, state.viewer);
            state.status = `Download started: ${filename}`;
        } catch (error) {
            if (modalState !== state) {
                return;
            }
            const message = error && error.message ? error.message : String(error);
            console.error("Could not download binary data", error);
            state.status = `Download failed: ${message}`;
        } finally {
            if (modalState === state) {
                state.downloading = false;
                updateModalControls();
            }
        }
    }

    async function getTableBinaryMetadata(viewer, tableName) {
        const requestGlobal = nextPythonName("binary_table_request");
        const functionGlobal = nextPythonName("binary_table_metadata");
        viewer.pyodide.globals.set(requestGlobal, JSON.stringify({ table: tableName }));
        try {
            const serialized = await viewer.pyodide.runPythonAsync(`
def ${functionGlobal}(_request_json):
    import json

    request = json.loads(_request_json)
    table = current_package.get(request["table"])
    if table is None:
        return json.dumps(
            {"binary_columns": [], "primary_key_columns": [], "rows": []}
        )

    binary_columns = [
        column.name for column in table.columns if column.type == "binary"
    ]
    key_indices = table.primary_key_indices()
    key_columns = [table.columns[index].name for index in key_indices]
    rows = []
    for row in table:
        primary_keys = [row[name] for name in key_columns]
        available = False
        unavailable_reason = None
        if not key_columns:
            unavailable_reason = "The table has no primary key"
        elif not all(isinstance(value, (str, int)) for value in primary_keys):
            unavailable_reason = "The row has an invalid primary-key value"
        else:
            logical_name = ".".join(
                str(value) for value in (table.name, *primary_keys)
            )
            stream_name = pymsi.streamname.encode_unicode(logical_name, False)
            available = current_package.ole.exists(stream_name)
            if not available:
                unavailable_reason = "The referenced OLE stream is missing"
        rows.append(
            {
                "primary_keys": primary_keys,
                "available": available,
                "unavailable_reason": unavailable_reason,
            }
        )

    return json.dumps(
        {
            "binary_columns": binary_columns,
            "primary_key_columns": key_columns,
            "rows": rows,
        },
        ensure_ascii=False,
    )

${functionGlobal}(${requestGlobal})
`);
            return JSON.parse(serialized);
        } finally {
            viewer.pyodide.globals.delete(requestGlobal);
            viewer.pyodide.globals.delete(functionGlobal);
        }
    }

    async function enhanceSelectedTable(viewer, selectedTable) {
        if (!selectedTable || selectedTable !== viewer.tableSelector.value) {
            return;
        }
        let metadata;
        try {
            metadata = await getTableBinaryMetadata(viewer, selectedTable);
        } catch (error) {
            console.error(`Could not inspect binary columns in ${selectedTable}`, error);
            return;
        }
        if (!metadata.binary_columns || !metadata.binary_columns.length) {
            return;
        }
        if (selectedTable !== viewer.tableSelector.value) {
            return;
        }
        const headerCells = Array.from(viewer.tableHeader.querySelectorAll("th"));
        const columnIndexes = new Map(
            headerCells.map((cell, index) => [cell.textContent, index]),
        );
        const rows = Array.from(viewer.tableContent.querySelectorAll("tr"));
        rows.forEach((row, rowIndex) => {
            const rowMetadata = metadata.rows[rowIndex];
            if (!rowMetadata) {
                return;
            }
            for (const columnName of metadata.binary_columns) {
                const columnIndex = columnIndexes.get(columnName);
                if (columnIndex === undefined || !row.children[columnIndex]) {
                    continue;
                }
                const cell = row.children[columnIndex];
                cell.classList.add("binary-cell");
                const marker = makeElement("span", "binary-value-marker", "<binary>");
                const request = {
                    kind: "table",
                    table: selectedTable,
                    primary_keys: rowMetadata.primary_keys,
                };
                const button = rowMetadata.available
                    ? makeInspectButton(request, "Inspect bytes")
                    : makeInspectButton(
                          null,
                          "Unavailable",
                          rowMetadata.unavailable_reason || "Binary stream unavailable",
                      );
                cell.replaceChildren(marker, button);
            }
        });
    }

    async function getFileRecords(viewer) {
        const functionGlobal = nextPythonName("binary_file_records");
        try {
            const serialized = await viewer.pyodide.runPythonAsync(`
def ${functionGlobal}():
    import json

    records = []
    for file_id, file in current_msi.files.items():
        file_name = str(file.name or file_id)
        if "|" in file_name:
            short_name, long_name = file_name.split("|", 1)
            file_name = long_name or short_name
        media = getattr(file, "media", None)
        cabinet_loaded = media is not None and getattr(media, "cabinet", None) is not None
        if cabinet_loaded:
            unavailable_reason = None
        else:
            unavailable_reason = (
                "This file is not stored in a loaded cabinet, so its bytes are not "
                "available in the browser viewer"
            )
        records.append(
            {
                "id": file_id,
                "name": file_name,
                "inspectable": cabinet_loaded,
                "unavailable_reason": unavailable_reason,
            }
        )
    return json.dumps(records, ensure_ascii=False)

${functionGlobal}()
`);
            return JSON.parse(serialized);
        } finally {
            viewer.pyodide.globals.delete(functionGlobal);
        }
    }

    async function enhanceFiles(viewer) {
        let files;
        try {
            files = await getFileRecords(viewer);
        } catch (error) {
            console.error("Could not prepare file inspection links", error);
            return;
        }
        viewer._pymsiBinaryFileRecords = new Map(
            files.map((file) => [String(file.id), file]),
        );
        if (!files.length) {
            return;
        }
        const table = document.getElementById("files-table");
        const header = table
            ? table.querySelector("thead tr") || table.querySelector("tr")
            : null;
        if (header && !header.querySelector(".binary-inspect-header")) {
            header.appendChild(makeElement("th", "binary-inspect-header", "Inspect"));
        }
        const emptyCell = viewer.filesList.querySelector('td[colspan="5"]');
        if (emptyCell) {
            emptyCell.colSpan = 6;
        }
        const rows = Array.from(viewer.filesList.querySelectorAll("tr"));
        rows.forEach((row, index) => {
            const file = files[index];
            if (!file || row.querySelector(".binary-file-cell")) {
                return;
            }
            row.dataset.fileId = String(file.id);
            const cell = makeElement("td", "binary-file-cell");
            if (file.inspectable) {
                cell.appendChild(
                    makeInspectButton({
                        kind: "file",
                        file_id: file.id,
                        display_name: file.name,
                    }),
                );
            } else {
                cell.appendChild(
                    makeInspectButton(
                        null,
                        "Unavailable",
                        file.unavailable_reason || "File bytes unavailable",
                    ),
                );
            }
            row.appendChild(cell);
        });
        if (table) {
            viewer.enhanceTable(table);
        }
    }

    async function getStreamNames(viewer) {
        if (Array.isArray(viewer._pymsiBinaryStreamNames)) {
            return viewer._pymsiBinaryStreamNames;
        }
        const functionGlobal = nextPythonName("binary_stream_names");
        try {
            const serialized = await viewer.pyodide.runPythonAsync(`
def ${functionGlobal}():
    import json

    names = []
    for child in current_package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(child.name)
        if not is_table:
            names.append(name)
    return json.dumps(names, ensure_ascii=False)

${functionGlobal}()
`);
            viewer._pymsiBinaryStreamNames = JSON.parse(serialized);
            return viewer._pymsiBinaryStreamNames;
        } finally {
            viewer.pyodide.globals.delete(functionGlobal);
        }
    }

    async function enhanceStreams(viewer) {
        if (!viewer.streamsContent) {
            return;
        }
        let names;
        try {
            names = await getStreamNames(viewer);
        } catch (error) {
            console.error("Could not prepare stream inspection links", error);
            return;
        }
        const table = viewer.streamsContent.querySelector("table");
        if (!table || !names.length) {
            return;
        }
        const rows = Array.from(table.querySelectorAll("tr"));
        if (!rows.length) {
            return;
        }
        const header = rows[0];
        if (!header.querySelector(".binary-inspect-header")) {
            header.appendChild(makeElement("th", "binary-inspect-header", "Inspect"));
        }
        rows.slice(1).forEach((row, index) => {
            const name = names[index];
            if (name === undefined || row.querySelector(".binary-stream-cell")) {
                return;
            }
            row.dataset.streamName = String(name);
            const cell = makeElement("td", "binary-stream-cell");
            cell.appendChild(
                makeInspectButton({ kind: "stream", stream_name: name }),
            );
            row.appendChild(cell);
        });
    }

    function fileUnavailableReason(viewer, fileId) {
        const records = viewer && viewer._pymsiBinaryFileRecords;
        if (!(records instanceof Map)) {
            return null;
        }
        const record = records.get(String(fileId));
        if (!record || record.inspectable) {
            return null;
        }
        return record.unavailable_reason || "File bytes unavailable";
    }

    function enhanceAnalysisReferences(root = document, viewer = null) {
        root.querySelectorAll(
            ".analysis-data-reference[data-binary-request]",
        ).forEach((row) => {
            if (row.querySelector(".binary-reference")) {
                return;
            }
            let request;
            try {
                request = JSON.parse(row.dataset.binaryRequest);
            } catch (error) {
                console.error("Invalid analysis binary reference", error);
                return;
            }
            if (request.kind === "file" && !request.display_name) {
                const record = viewer?._pymsiBinaryFileRecords?.get(
                    String(request.file_id),
                );
                if (record?.name) {
                    request = { ...request, display_name: record.name };
                }
            }
            const label = request.kind === "file" ? "Inspect file" : "Inspect payload";
            const disabledReason =
                request.kind === "file"
                    ? fileUnavailableReason(viewer, request.file_id)
                    : null;
            row.appendChild(
                makeInspectButton(
                    disabledReason ? null : request,
                    disabledReason ? "Unavailable" : label,
                    disabledReason,
                ),
            );
        });
    }

    function rememberViewer(viewer) {
        globalThis.pymsiViewer = viewer;
        const app = document.getElementById("msi-viewer-app");
        if (app) {
            app._pymsiViewerInstance = viewer;
        }
    }

    function installViewerMethods() {
        if (typeof MSIViewer === "undefined") {
            console.warn("pymsi binary viewer: MSIViewer is not available");
            return;
        }
        if (MSIViewer.prototype._pymsiBinaryViewerInstalled) {
            return;
        }
        MSIViewer.prototype._pymsiBinaryViewerInstalled = true;

        const originalLoadMsiFileFromArrayBuffer =
            MSIViewer.prototype.loadMsiFileFromArrayBuffer;
        if (typeof originalLoadMsiFileFromArrayBuffer === "function") {
            MSIViewer.prototype.loadMsiFileFromArrayBuffer =
                async function loadMsiWithFreshBinaryState(...args) {
                    rememberViewer(this);
                    closeModal();
                    this._pymsiBinaryStreamNames = null;
                    this._pymsiBinaryFileRecords = null;
                    return originalLoadMsiFileFromArrayBuffer.apply(this, args);
                };
        }

        const originalLoadTableData = MSIViewer.prototype.loadTableData;
        MSIViewer.prototype.loadTableData = async function loadTableDataWithBinaryLinks(
            ...args
        ) {
            rememberViewer(this);
            const selectedTable = this.tableSelector.value;
            const result = await originalLoadTableData.apply(this, args);
            await enhanceSelectedTable(this, selectedTable);
            return result;
        };

        const originalLoadFilesList = MSIViewer.prototype.loadFilesList;
        MSIViewer.prototype.loadFilesList = async function loadFilesListWithBinaryLinks(
            ...args
        ) {
            rememberViewer(this);
            const result = await originalLoadFilesList.apply(this, args);
            await enhanceFiles(this);
            return result;
        };

        const originalGetAllStreamNames = MSIViewer.prototype.getAllStreamNames;
        if (typeof originalGetAllStreamNames === "function") {
            MSIViewer.prototype.getAllStreamNames =
                async function getAllStreamNamesForBinaryViewer(...args) {
                    rememberViewer(this);
                    const result = await originalGetAllStreamNames.apply(this, args);
                    this._pymsiBinaryStreamNames = Array.from(
                        result || [],
                        (name) => String(name),
                    );
                    return result;
                };
        }

        const originalLoadStreams = MSIViewer.prototype.loadStreams;
        MSIViewer.prototype.loadStreams = async function loadStreamsWithBinaryLinks(
            ...args
        ) {
            rememberViewer(this);
            const result = await originalLoadStreams.apply(this, args);
            await enhanceStreams(this);
            return result;
        };

        const originalLoadSecurityAnalysis = MSIViewer.prototype.loadSecurityAnalysis;
        if (typeof originalLoadSecurityAnalysis === "function") {
            MSIViewer.prototype.loadSecurityAnalysis =
                async function loadAnalysisWithBinaryLinks(...args) {
                    rememberViewer(this);
                    const result = await originalLoadSecurityAnalysis.apply(this, args);
                    enhanceAnalysisReferences(
                        document.getElementById("analysis-content") || document,
                        this,
                    );
                    return result;
                };
        }
    }

    function installClickHandler() {
        document.addEventListener("click", (event) => {
            if (!(event.target instanceof Element)) {
                return;
            }
            const button = event.target.closest(
                ".binary-reference[data-binary-request]",
            );
            if (!button || button.disabled) {
                return;
            }
            event.preventDefault();
            let request;
            try {
                request = JSON.parse(button.dataset.binaryRequest);
            } catch (error) {
                console.error("Invalid binary viewer request", error);
                return;
            }
            const viewer =
                button.closest("#msi-viewer-app")?._pymsiViewerInstance ||
                globalThis.pymsiViewer;
            if (viewer) {
                void openRequest(viewer, request);
                return;
            }
            showModal(
                requestLabel(request),
                "Viewer instance unavailable",
                "Reload the page and load the MSI again.",
                true,
            );
        });
    }

    document.addEventListener("pymsi-analysis-rendered", (event) => {
        const viewer =
            event.detail?.container
                ?.closest("#msi-viewer-app")
                ?._pymsiViewerInstance || globalThis.pymsiViewer || null;
        enhanceAnalysisReferences(event.detail?.container || document, viewer);
    });

    installStyles();
    ensureModal();
    installViewerMethods();
    installClickHandler();
    enhanceAnalysisReferences();
})();
