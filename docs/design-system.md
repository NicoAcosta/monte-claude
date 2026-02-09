# MonteClaude Design System

## Colors

| Token          | Hex       | Usage                                     |
| -------------- | --------- | ----------------------------------------- |
| `--navy`       | `#0C1D39` | Primary background, dominant color (45%)  |
| `--crimson`    | `#B2171D` | Accent, mascot, CTA backgrounds (20%)     |
| `--gold`       | `#D7A640` | Accent, borders, labels, highlights (20%) |
| `--red-bright` | `#C21A17` | Secondary accent, sparingly (5%)          |
| `--black`      | `#0A0A0A` | Text on light backgrounds (5%)            |
| `--white`      | `#FAFAF5` | Text on dark backgrounds, light bg (5%)   |
| `--cream`      | `#F5F0E8` | Alt light background                      |
| `--gold-light` | `#E8C76A` | Hover states, gradient endpoint           |
| `--navy-light` | `#1A2E52` | Cards, elevated surfaces on navy          |

## Typography

```css
/* Display — headlines, hero text, wordmark */
font-family: 'Source Serif 4', Georgia, serif;
/* weights: 700, 800, 900 */

/* Headlines — section labels, nav, badges (always uppercase, letter-spacing: 0.3em) */
font-family: 'Bebas Neue', Impact, sans-serif;

/* Body — copy, UI, descriptions */
font-family: 'DM Sans', 'Helvetica Neue', sans-serif;
/* weights: 400 body, 500 emphasis, 600-700 strong */
```

Google Fonts import:

```html
<link
	href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900;1,8..60,200..900&display=swap"
	rel="stylesheet" />
```

## Spacing

Base-8 scale: `8 · 16 · 24 · 32 · 48 · 64 · 96` px

## Border Radius

- Cards/containers: `16px`
- Buttons: `8px`
- Badges/tags: `4px`
- Full round: `9999px`

## Logo Assets

- **Primary**: horizontal lockup (mark + wordmark) — default for headers, web, social
- **Secondary**: standalone mark — favicons, avatars, app icons
- Min clear space: 1x mark height around all sides
- Never separate mark from wordmark in the lockup

## Key Rules

- Navy is the dominant background color
- Pair crimson with gold for max brand impact
- Never use crimson + bright red adjacent without navy separation
- Bebas Neue is headlines only, always uppercase
- Source Serif 4 for the wordmark — never recreate in another font
