# Frontend Changes

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
