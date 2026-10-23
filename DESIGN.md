# DESIGN.md: YT-DLP Web Downloader

## 1. Visual Identity

**Name:** YT Downloader
**Aesthetic:** Modern, dark-themed dashboard with glassmorphism accents. Clean, minimal, functional.
**Tone:** Professional tool — not playful, not corporate. Efficient and clear.

## 2. Design Tokens

### Colors

```css
:root {
  /* Background */
  --bg-primary: #0f0f14;
  --bg-secondary: #1a1a24;
  --bg-tertiary: #24243a;
  --bg-glass: rgba(30, 30, 50, 0.7);
  --bg-glass-border: rgba(255, 255, 255, 0.08);

  /* Accent */
  --accent-primary: #6c5ce7;
  --accent-primary-hover: #7d6ff0;
  --accent-secondary: #00cec9;
  --accent-gradient: linear-gradient(135deg, #6c5ce7, #00cec9);

  /* Text */
  --text-primary: #e8e8f0;
  --text-secondary: #9090a8;
  --text-muted: #606078;

  /* Status */
  --status-queued: #fdcb6e;
  --status-running: #0984e3;
  --status-completed: #00b894;
  --status-failed: #d63031;
  --status-cancelled: #636e72;

  /* Borders & Surfaces */
  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-input: rgba(255, 255, 255, 0.12);
  --border-focus: #6c5ce7;
  --surface-hover: rgba(108, 92, 231, 0.08);
}
```

### Typography

```css
:root {
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;

  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.875rem;   /* 14px */
  --text-base: 1rem;     /* 16px */
  --text-lg: 1.125rem;   /* 18px */
  --text-xl: 1.25rem;    /* 20px */
  --text-2xl: 1.5rem;    /* 24px */
  --text-3xl: 2rem;      /* 32px */

  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;

  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;
}
```

### Spacing

```css
:root {
  --space-1: 0.25rem;  /* 4px */
  --space-2: 0.5rem;   /* 8px */
  --space-3: 0.75rem;  /* 12px */
  --space-4: 1rem;     /* 16px */
  --space-5: 1.25rem;  /* 20px */
  --space-6: 1.5rem;   /* 24px */
  --space-8: 2rem;     /* 32px */
  --space-10: 2.5rem;  /* 40px */
  --space-12: 3rem;    /* 48px */
}
```

### Shape

```css
:root {
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 30px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 20px rgba(108, 92, 231, 0.3);
}
```

### Transitions

```css
:root {
  --transition-fast: 150ms ease;
  --transition-base: 250ms ease;
  --transition-slow: 400ms ease;
}
```

## 3. Layout

### Desktop (≥1024px)

- Max content width: 900px, centered.
- Header: logo/name left, health indicator right.
- Tab bar: Single | Bulk mode selector.
- Input section: URL input, quality/format controls, submit button.
- Job queue: vertical list of job cards.
- Downloads: completed files list.

### Tablet (768px–1023px)

- Same layout, full-width cards.
- Reduced padding.

### Mobile (< 768px)

- Single column layout.
- Stacked form controls.
- Full-width buttons.
- Compact job cards.

## 4. Components

### 4.1 Header

- App name "YT Downloader" with gradient text.
- Small health status dot (green/red) with tooltip.
- Subtle bottom border.

### 4.2 Tab Switcher

- Two tabs: "Single Download" and "Bulk Download".
- Active tab has accent underline and accent text.
- Inactive tab has muted text.
- Keyboard accessible (Tab + Enter/Space).

### 4.3 URL Input (Single)

- Full-width text input.
- Placeholder: "Paste YouTube video or playlist URL..."
- Validation message below: green check or red error.
- Glass-style card background.

### 4.4 Bulk URL Input

- Full-width textarea, 6 rows minimum.
- Placeholder: "Paste YouTube URLs, one per line..."
- Validation summary below: "X valid · X invalid · X duplicates".
- Individual line errors shown.
- Glass-style card background.

### 4.5 Quality & Format Controls

- Horizontal group: Quality dropdown + Format toggle.
- Quality dropdown: Best, 1080p, 720p, 480p.
- Format toggle: Video | Audio pill selector.
- Audio sub-options: Best Audio, MP3.

### 4.6 Submit Button

- Full-width or right-aligned primary button.
- Gradient background with hover glow.
- Disabled state during submission (muted, spinner).
- Text changes: "Download" → "Submitting..." → "Download".

### 4.7 Job Card

- Glass card with border.
- Left: status indicator dot (color-coded).
- Title: video title or URL (truncated).
- Status badge: QUEUED | RUNNING | COMPLETED | FAILED.
- Progress bar (when running): gradient fill with percentage.
- Stats row: speed, ETA, size.
- Actions: Download button (completed) | Retry button (failed).
- Expand/collapse for details.

### 4.8 Progress Bar

- Height: 6px, full-width within card.
- Background: --bg-tertiary.
- Fill: accent gradient, animated shimmer when running.
- Indeterminate: animated pulse when percentage unknown.

### 4.9 Batch Summary Card

- Shows batch ID, total/completed/failed/queued counts.
- Expandable to show individual job cards.

### 4.10 Empty State

- Centered illustration or icon.
- "No downloads yet" message.
- Subtle call-to-action text.

### 4.11 Error Messages

- Red-tinted glass card.
- Error icon + message text.
- Dismissible.
- Never shows stack traces or internal paths.

### 4.12 Toast Notifications

- Top-right positioned.
- Auto-dismiss after 5 seconds.
- Success (green), Error (red), Info (blue) variants.

## 5. Accessibility

- All interactive elements focusable via keyboard.
- Visible focus rings using --border-focus color.
- ARIA labels on icon-only buttons.
- ARIA live regions for job status updates.
- Sufficient contrast ratios (WCAG AA minimum).
- Form labels associated with inputs.
- Error messages linked to inputs via aria-describedby.
- No information conveyed by color alone (status also has text labels).

## 6. States

### Loading States

- Skeleton pulse animation for initial load.
- Button spinner during submission.
- Progress bar animation during download.

### Error States

- Inline validation errors (red text below inputs).
- Toast for network errors.
- Job card error display.
- Global error banner for system issues.

### Empty States

- Empty job queue: friendly message with gradient icon.
- No completed downloads: subtle prompt.

### Success States

- Completed job: green status, download button appears.
- Toast confirmation on submission.
