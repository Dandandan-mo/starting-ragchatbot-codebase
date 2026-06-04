# Frontend Changes: Dark/Light Mode Toggle Button, Light Theme & JS Functionality

## Summary

Added a dark/light mode toggle button (top-right, sun/moon icons), a complete accessibility-compliant light theme, and robust JavaScript that handles theme toggling, OS preference detection, flash-of-wrong-theme prevention, and runtime preference sync.

---

## Feature 1: Toggle Button

### `frontend/index.html`
- Added `<button class="theme-toggle" id="themeToggle" aria-pressed="false">` directly inside `<body>`, before `.container`, so it is fixed to the viewport and not affected by the layout stack.
- Contains two inline SVG icons: **moon** (visible in dark mode) and **sun** (visible in light mode).
- `aria-label`, `title`, and `aria-pressed` attributes provided for screen readers and keyboard users.

### `frontend/style.css` (toggle)
- Added `--toggle-bg`, `--toggle-hover-bg`, `--toggle-color`, `--toggle-hover-color` variables in `:root` (and overridden in `html.light-mode`).
- `.theme-toggle`: 40×40px fixed-position circle, top-right at `1rem` offset, z-index 1000. Hover scales to 1.1×; active scales to 0.95×; focus shows 3px `--focus-ring` outline.
- Icon visibility: `.icon-moon` block by default; `.icon-sun` displayed only when `html.light-mode` is present.

---

## Feature 2: Light Theme Variant

### Color system (`frontend/style.css`)

All theme colors are driven by CSS custom properties. The dark mode defaults live in `:root`; `html.light-mode` overrides every property that changes.

#### New variables added to `:root` (dark defaults)
| Variable | Dark value | Purpose |
|---|---|---|
| `--assistant-message` | `#1e293b` | Assistant bubble background (was implicit via `--surface`) |
| `--welcome-shadow` | `rgba(0,0,0,0.2)` | Welcome message drop-shadow |
| `--code-bg` | `rgba(0,0,0,0.25)` | Inline code and pre block background |
| `--error-color` | `#f87171` | Error text |
| `--error-bg` | `rgba(239,68,68,0.1)` | Error banner background |
| `--error-border` | `rgba(239,68,68,0.25)` | Error banner border |
| `--success-color` | `#4ade80` | Success text |
| `--success-bg` | `rgba(34,197,94,0.1)` | Success banner background |
| `--success-border` | `rgba(34,197,94,0.25)` | Success banner border |

#### Light mode overrides (`html.light-mode`)
| Variable | Light value | Rationale |
|---|---|---|
| `--background` | `#f1f5f9` | Slate-100; soft off-white, avoids harsh pure white |
| `--surface` | `#ffffff` | Sidebar and elevated surfaces |
| `--surface-hover` | `#e2e8f0` | Hover state for interactive surfaces |
| `--text-primary` | `#0f172a` | Slate-900; near-black, ~16:1 contrast on `--background` |
| `--text-secondary` | `#475569` | Slate-600; ~6:1 contrast on `--background` (AA+) |
| `--border-color` | `#cbd5e1` | Slate-300; visible but subtle on white |
| `--assistant-message` | `#e8eef5` | Distinguishes assistant bubbles from the `#f1f5f9` page background |
| `--welcome-shadow` | `rgba(0,0,0,0.08)` | Lighter shadow on white surfaces |
| `--code-bg` | `rgba(0,0,0,0.06)` | Very light tint; readable code on light background |
| `--error-color` | `#b91c1c` | Red-700; ~6:1 contrast on white (AA) |
| `--error-bg` | `rgba(220,38,38,0.08)` | Subtle red tint |
| `--error-border` | `rgba(220,38,38,0.2)` | Matching border |
| `--success-color` | `#15803d` | Green-700; ~5:1 contrast on white (AA) |
| `--success-bg` | `rgba(22,163,74,0.08)` | Subtle green tint |
| `--success-border` | `rgba(22,163,74,0.2)` | Matching border |
| `--toggle-bg` | `#e2e8f0` | Slate-200 button background |
| `--toggle-hover-bg` | `#cbd5e1` | Slate-300 hover |
| `--toggle-color` | `#475569` | Icon color |
| `--toggle-hover-color` | `#0f172a` | Icon color on hover |

`--primary-color: #2563eb` and `--primary-hover: #1d4ed8` are unchanged — both pass WCAG AA on the light background (~4.9:1 and ~6.3:1 respectively).

### Hardcoded color fixes
- **Assistant message background**: changed from `var(--surface)` → `var(--assistant-message)`, so bubbles are distinguishable from the page background in light mode.
- **Welcome message background**: same fix; shadow uses `var(--welcome-shadow)` instead of hardcoded `rgba(0,0,0,0.2)`.
- **Code/pre blocks**: `rgba(0,0,0,0.2)` → `var(--code-bg)`, adaptive per theme.
- **Error/success banners**: hardcoded hex/rgba values → `var(--error-*)` / `var(--success-*)` variables.

### Smooth transitions
Targeted transition rule (`background-color`, `border-color`, `color`, `box-shadow` over 0.3s ease) applied to: `body`, `.sidebar`, `.chat-main`, `.chat-container`, `.chat-messages`, `.chat-input-container`, `.message-content`, `.source-link`, `.stat-item`, `.suggested-item`, `.new-chat-btn`, `#chatInput`, `#sendButton`.

---

## Feature 3: JavaScript Functionality

### Anti-flash-of-wrong-theme (FOUC prevention) — `frontend/index.html`
An inline `<script>` is placed in `<head>` **before** the stylesheet link. It runs synchronously during HTML parsing — before any paint — so the correct theme class is on `<html>` from the very first render frame:

```js
(function () {
  var saved = localStorage.getItem('theme');
  var preferLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
  if (saved === 'light' || (!saved && preferLight)) {
    document.documentElement.classList.add('light-mode');
  }
}());
```

Logic: explicit user choice (`localStorage`) takes priority; if no saved choice, the OS `prefers-color-scheme: light` media query is the default.

### CSS selector scope — `frontend/style.css`
Changed all three `body.light-mode` selectors to `html.light-mode`. This is required so the anti-FOUC inline script (which targets `document.documentElement` = `<html>`) correctly activates the light theme variables before `<body>` even exists in the DOM.

### `initTheme()` — `frontend/script.js`
Called first in `DOMContentLoaded`. Now has two responsibilities:
1. **Sync `aria-pressed`** on the toggle button to match whichever state the anti-FOUC script applied.
2. **OS preference listener**: attaches a `change` handler on the `prefers-color-scheme: light` media query. If the OS switches theme at runtime and the user has not saved an explicit preference, the page theme follows automatically via `applyTheme()`.

### `applyTheme(light)` — `frontend/script.js`
Helper that sets `html.light-mode` and syncs `aria-pressed` atomically. Used by the OS preference listener.

### `toggleTheme()` — `frontend/script.js`
- Operates on `document.documentElement` (not `document.body`) so it matches the CSS selectors and anti-FOUC script.
- Saves `'light'` or `'dark'` to `localStorage` after each click (explicit user choice overrides OS preference).
- Updates `aria-pressed` so screen readers announce the new state.

---

## Full Behavior Summary

| Scenario | Result |
|---|---|
| First load, no saved preference, OS = dark | Dark mode, no flash |
| First load, no saved preference, OS = light | Light mode, no flash |
| First load, saved preference = `'light'` | Light mode, no flash |
| First load, saved preference = `'dark'` | Dark mode, no flash |
| Click toggle | Theme switches with 0.3s CSS transition; saved to `localStorage` |
| OS changes theme while page is open, no saved preference | Page follows OS theme |
| OS changes theme while page is open, user has saved a preference | Page ignores OS change |
| Keyboard Tab + Enter/Space on button | Toggle fires; `aria-pressed` updates for screen readers |

---

## Code Quality Tooling Setup

### What was added

**Prettier** — automatic code formatter for JavaScript, CSS, and HTML (the frontend equivalent of Python's `black`).

### New files

| File | Purpose |
|------|---------|
| `package.json` | Node project manifest; declares Prettier as a dev dependency and defines `format`, `format:check`, and `quality` npm scripts |
| `.prettierrc` | Prettier configuration: 4-space indentation, single quotes, 80-char print width, LF line endings, ES5 trailing commas |
| `scripts/check-frontend.sh` | Shell script that installs deps (if needed) and runs `prettier --check` across all frontend files; exits non-zero on formatting violations |

### Formatting rules (`.prettierrc`)

```json
{
    "printWidth": 80,
    "tabWidth": 4,
    "useTabs": false,
    "semi": true,
    "singleQuote": true,
    "trailingComma": "es5",
    "bracketSpacing": true,
    "htmlWhitespaceSensitivity": "css",
    "endOfLine": "lf"
}
```

### Formatting fixes applied to existing files

- `frontend/script.js` — removed duplicate blank lines in `setupEventListeners` (before the suggested-questions listener block and after the closing brace)
- `frontend/style.css` — removed a stale inline comment (`/* Remove max-height to show all titles without scrolling */`) in `.course-titles` that described a one-time edit rather than a lasting constraint

### How to use

```bash
# Install Node dependencies (one-time)
npm install

# Check formatting (CI / pre-commit)
npm run format:check
# or
./scripts/check-frontend.sh

# Auto-fix formatting
npm run format
```
