# Screenshots for the frontend CSS layer-order fix

Image-only branch, not meant for merging. The PR body links these files.

- `before_*`: frontend/src/main.tsx as on main f61875a7 (App imported before index.css).
- `after_*`: commit ea9e182e (index.css imported first).
- Taken with Playwright on the Vite dev server (demo sign-in, no backend, so in-app data shows its error state).
- desktop = 1366×860 at device scale 2; mobile = iPhone 13 emulation.
