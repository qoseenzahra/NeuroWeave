# Pipeline canvas layout and connection visibility

## Read-only details and independent copies

Pipeline details now open a read-only canvas with node selection, parameter and
port inspection, shared-input links, connection focus, zoom and panning. The
viewer never saves a draft. Built-in pipelines cannot be edited, moved, rewired,
archived or overwritten. The backend also rejects updates to built-in IDs.

“Create from this Pipeline” opens an independent editable draft with a new
recovery key and no association to the original ID or version. Publishing creates
a new user Pipeline at v1. Method parameter defaults, fixed values, ordered links,
shared external inputs and conditional stages are retained. Conditional stages
keep their Pipeline control parameters; the copy editor exposes those controls.
Existing task confirmation and execution behavior remains unchanged.

The read-only `/api/library/pipelines/{id}/source?version=...` endpoint projects
the immutable execution graph into authoring source without writing to storage.
All 24 built-in sources are covered by compilation and preservation regressions.

Deployed to the existing port 3002 frontend on 2026-09-27. Revision:
`canvas-ui-e219f8f10d81`. No backend API or execution behavior changed.

## Behavior

- The editor uses the whole browser viewport. Method palette and parameter inspector
  can be hidden independently. Crossing below 1100 px closes the docks; users can
  reopen one dock at a time. Name/description stays collapsed by default.
- Validation has a separate, collapsible row with its own scroll area, capped at
  25% of viewport height. It cannot overlay the canvas.
- Canvas supports 2–200% zoom, a slider, zoom buttons, Ctrl/Command-wheel or trackpad
  pinch, fit-all, focus-selected-node, and reset. Focus the canvas for + / - / 0 / F.
- Background drag pans; node-header drag moves a step. Zoom leaves saved graph
  coordinates unchanged. Automatic arrangement reserves wider routing corridors.
- Connections have separate colors and orthogonal candidate routes that favor
  avoiding node bodies. Shared inputs use dashed purple links. Hover/click highlights
  both endpoint ports and the chosen edge. The connection list states numbered steps
  and exact input/output labels, including repeated methods. Arbitrary dense graphs
  may still cross; focused edges render last while other edges fade.

## Module responsibilities

- `canvasGeometry.ts`: pure coordinate, fit, zoom anchoring and bounded routing.
- `useCanvasViewport.ts`: viewport events, scroll/zoom coordination and cleanup.
- `canvasConnections.ts`: graph bindings to renderable, labeled connections.
- `PipelineConnections.tsx`: edge rendering, focus and connection list.
- `PipelineCanvasNode.tsx`: node headers and conditional input/output ports.
- `PipelineCanvas.tsx`: gestures and coordination with the editor callbacks.
- `PipelineValidationPanel.tsx`: independent read-only validation presentation.

## Verification

- Frontend tests: 53 passed (4 new geometry/connection regressions).
- TypeScript/Vite production build passed; ESLint passed for changed canvas modules.
- Browser checks at 1440×1000 and 1024×768 using an isolated local database:
  three tissue-response connections plus shared DWI; node drag; automatic arrangement;
  zoom buttons and fit; selected-edge fading/endpoint labels; validation expansion and
  collapse; sidebar hiding and automatic hiding after resize. No browser errors.
- Measured canvas and validation bounds do not overlap. Scaled endpoints match port
  centers within 1 CSS pixel at the tested scale. Wheel/pinch anchoring has geometry
  regression coverage; physical trackpad gesture hardware was not separately tested.
- Temporary local preview stopped after testing. No model API calls or Runner jobs.
- Server source compared with prior release: no remote-only or divergent files.
  15 frontend source/test files and 5 static files installed; all hashes and served
  HTTP bytes verified. Backend PIDs and container IDs/start times unchanged. The
  server UI was not directly browser-tested; its static assets and APIs were checked
  from the server, while interactions used the same local build.

## Deployment / rollback

Release directory:
`/home/hipeson/.cache/neuroweave/canvas-ui-e219f8f10d81`

Live directory:
`/home/hipeson/.cache/neuroweave/methods-webtest-20260922`

Publisher backs up overwritten files, checks concurrent changes, writes hashed assets
before atomically replacing `index.html`, retains older assets, and verifies service
identities. No service restart, file removal, database mutation or task submission.
The frontend version is served at `/__frontend-version.json`; the backend health
release intentionally retains its own revision.

Rollback if required, provided no later release has replaced these files:

```bash
python3 /home/hipeson/.cache/neuroweave/canvas-ui-e219f8f10d81/publish.py --rollback /home/hipeson/.cache/neuroweave/canvas-ui-e219f8f10d81/backup-20260927T100251375901Z
```

This UI update did not require restarting any service. The source was subsequently
committed to the branch in `9370fed`; that push did not redeploy the backend. The
existing Vite large-bundle warning remains.
