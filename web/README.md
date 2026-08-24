# Building the self-hosted MSI viewer

The files in `web/viewer/` are the canonical browser UI sources. They are shared by the ReadTheDocs page and both downloadable standalone variants.

## Build variants

From the repository root:

```console
python tools/build_web_viewer.py --target cdn
python tools/build_web_viewer.py --target bundled
```

The default output directory is `dist/web-viewer/`:

- `pymsi-viewer-cdn/` uses pinned CDN JavaScript/Pyodide assets and installs pymsi from PyPI at runtime.
- `pymsi-viewer-bundled/` contains Pyodide, the JavaScript dependencies, the current pymsi wheel, its Python dependency, and the example MSI. It makes no runtime network requests.
- Matching `.zip` files are generated beside the directories.

Use `--target all` to build both standalone variants and the generated ReadTheDocs embed. The bundled build downloads pinned dependencies into `.cache/web-viewer/`; subsequent builds reuse that cache. `--offline` requires every downloaded input to already be present in the cache.

The bundled build needs the project build dependencies (`python -m pip install build`) because it packages the current checkout into a wheel. A prebuilt wheel can instead be supplied with `--pymsi-wheel path/to/pymsi.whl`.

An `--offline` build never invokes a network-dependent wheel build. It therefore needs either a pymsi wheel already cached for the same source/tag identity or an explicit `--pymsi-wheel` argument, in addition to the downloaded browser assets already being present in the cache.

## Serving the viewer

Browsers do not allow Pyodide to load its companion files reliably from a `file://` URL. Serve either directory over HTTP, for example:

```console
python -m http.server --directory dist/web-viewer/pymsi-viewer-bundled 8000
```

Then open `http://localhost:8000/`.

The host must serve `.wasm` files as `application/wasm`. Python's built-in server and common current web servers do this by default.

## Light and dark themes

The standalone stylesheet follows `prefers-color-scheme`. A host page can force a theme by setting `data-theme="light"` or `data-theme="dark"` on the `<html>` element.

## ReadTheDocs

`python tools/build_web_viewer.py --target rtd` writes the generated embed to `docs/_generated/` and its assets to `docs/_static/msi_viewer/`. The ReadTheDocs-only flyout overlap workaround is added only to this target.
