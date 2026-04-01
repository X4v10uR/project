# Design System Strategy: The Financial Architect

## 1. Overview & Creative North Star
The "Creative North Star" for this design system is **The Financial Architect**. 

Subscription management is often chaotic and cluttered; this system restores order through a high-end, editorial lens. We move beyond "SaaS-generic" by rejecting the standard grid in favor of **intentional asymmetry** and **tonal depth**. The goal is to make the user feel like they are looking at a premium financial broadsheet—authoritative, clean, and meticulously organized. We achieve this by utilizing expansive white space (using the `20` and `24` spacing tokens) and a typography scale that treats data as hero content.

## 2. Colors: Tonal Atmosphere
Our palette is anchored by a vibrant Indigo (`primary: #3525cd`), but its power comes from how it interacts with our sophisticated neutral scale.

### The "No-Line" Rule
**Borders are a failure of layout.** To maintain a premium, architectural feel, designers are strictly prohibited from using 1px solid borders for sectioning. Boundaries must be defined solely through background color shifts. For example, a `surface-container-low` section sitting on a `surface` background creates a clear, sophisticated edge without the visual "noise" of a stroke.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—like stacked sheets of heavy-weight cotton paper. 
- **Base Level:** `surface` (#f7f9fb)
- **Primary Layout Blocks:** `surface-container-low` (#f2f4f6)
- **Interactive Cards:** `surface-container-lowest` (#ffffff)
- **Active/Hover States:** `surface-container-high` (#e6e8ea)

### The Glass & Gradient Rule
To move beyond a "flat" feel, floating elements (like the 'Live Summary' preview) should utilize **Glassmorphism**. Apply a semi-transparent `surface-container-lowest` with a `backdrop-filter: blur(12px)`. For main CTAs, use a subtle linear gradient from `primary` (#3525cd) to `primary_container` (#4f46e5) to provide a "soul" and depth that flat hex codes cannot achieve.

## 3. Typography: Editorial Authority
We pair the structural precision of **Inter** for utility with the sophisticated character of **Manrope** for display.

- **The Display Scale:** Use `display-lg` and `display-md` (Manrope) for total monthly spends or major category headers. These should feel like headlines in a premium magazine—confident and large.
- **The Functional Scale:** Use `body-md` (Inter) for all form labels and input text. Inter’s high x-height ensures readability even at the `label-sm` scale for metadata like "Next billing date."
- **Visual Rhythm:** Always use `on_surface_variant` (#464555) for secondary information to create a clear "read-order" hierarchy against the high-contrast `on_surface` (#191c1e) titles.

## 4. Elevation & Depth: Tonal Layering
Traditional box-shadows are often messy. In this system, we convey hierarchy through **Tonal Layering**.

- **The Layering Principle:** Depth is achieved by "stacking." A `surface-container-lowest` card placed on a `surface-container-low` background creates a soft, natural lift. 
- **Ambient Shadows:** If a "floating" effect is required (e.g., a color picker popover), use an extra-diffused shadow: `box-shadow: 0 12px 40px rgba(25, 28, 30, 0.06)`. The shadow color must be a tinted version of `on-surface` to mimic natural light.
- **The "Ghost Border" Fallback:** If a boundary is required for accessibility, use the `outline-variant` token at 15% opacity. Never use 100% opaque borders.

## 5. Components: Precision Primitives

### The 'Live Summary' Card (Signature Component)
The centerpiece of the application. It must use the `xl` (0.75rem) roundedness scale. Use a `surface-container-lowest` base with a subtle `surface-tint` glow. No dividers allowed; separate the subscription name, price, and renewal date using `spacing-4` (1rem) vertical gaps.

### Buttons
- **Primary:** Gradient fill (`primary` to `primary_container`), `on_primary` text, `md` roundedness.
- **Secondary:** `secondary_container` background with `on_secondary_container` text. No border.
- **States:** On hover, shift the background to `primary_fixed_dim`.

### Input Fields & Color Pickers
- **Containers:** Use `surface-container-highest` for the input background to create an "inset" feel. 
- **Focus State:** Instead of a thick border, use a 2px `surface-tint` outer glow and shift the background to `surface-container-lowest`.
- **Color Pickers:** Circular swatches using the `full` roundedness scale, housed in a glassmorphic popover.

### Lists & Toggles
- **Forbid Dividers:** Use `spacing-2` of vertical white space and a subtle background shift (`surface-container-low`) on hover to define list items.
- **Toggles:** Use `primary` for the "on" state track and `surface-dim` for the "off" state. The "thumb" should always be `surface-container-lowest`.

## 6. Do’s and Don’ts

### Do
- **Do** use `spacing-16` or `spacing-20` for page margins to create an elite, spacious feel.
- **Do** use `tertiary` (#7e3000) for "Warning" or "Expiring Soon" states to provide a sophisticated alternative to standard "Error" reds.
- **Do** align data points (like prices) to a strict vertical axis for an "accounting ledger" level of precision.

### Don't
- **Don't** use 1px solid lines to separate content; use `surface` shifts or whitespace.
- **Don't** use pure black (#000000) for text; always use `on_surface` (#191c1e).
- **Don't** use "Standard" blue; stick strictly to the `primary` (#3525cd) Indigo to maintain brand distinction.