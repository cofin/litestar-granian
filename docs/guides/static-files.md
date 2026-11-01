# Static Files

Granian can serve static directories directly from Rust without routing static asset requests through the Python ASGI worker layer.

## Explicit Native Mounts

Pair every URL route prefix with one directory mount:

```bash
litestar --app docs.examples.app:app run --static-path-route /assets --static-path-mount docs/examples/static
```

The example directory contains:

```html
--8<-- "docs/examples/static/index.html"
```

Repeat both options in the same order for multiple mounts; their counts must match. Pass `--static-path-dir-to-file` to serve a directory index file such as `index.html` (enabling SPA HTML mode), or pass `--static-path-expires 0` to disable cache expiration headers.

## Provider Auto-Discovery

`GranianPlugin(static="auto")` inspects the Litestar application for exactly one registered plugin with a callable `get_static_server_config()` method. A valid native static configuration must provide:

- Local absolute URL routes
- Existing, non-empty directories
- One consistent directory-index value across mounts

If no provider is registered, multiple providers are present, the application is mounted under an ASGI sub-path, paths are unsafe, or the returned configuration is malformed, `GranianPlugin` logs a single `INFO` message and leaves Litestar's Python static router in place. Explicit `--static-path-route` and `--static-path-mount` CLI options always take precedence over auto-discovery.
