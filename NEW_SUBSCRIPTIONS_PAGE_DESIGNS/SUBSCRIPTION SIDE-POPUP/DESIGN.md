# The Design System: Editorial Clarity & Tonal Depth

## 1. Overview & Creative North Star
**The Creative North Star: "The Lucid Curator"**
Subscription management is often a chaotic, data-heavy experience of anxiety-inducing recurring costs. This design system rejects the "finance app" aesthetic of rigid grids and harsh borders. Instead, we embrace a high-end editorial approach. 

By utilizing intentional asymmetry, expansive white space (breathing room), and a sophisticated "yellow-on-neutral" palette, we transform data into a curated narrative. The layout should feel like a premium digital magazine: airy, authoritative, and frictionless. We achieve this by prioritizing **Tonal Layering** over structural containment, ensuring the UI feels like a seamless, living surface rather than a collection of widgets.

---

## 2. Colors
Our color strategy moves away from the "flat" web. We use the palette to create a sense of physical presence and sophisticated hierarchy.

### The "No-Line" Rule
**Borders are a failure of hierarchy.** Within this system, 1px solid borders for sectioning are strictly prohibited. Separation must be achieved through:
1.  **Background Shifts:** Placing a `surface-container-low` component on a `surface` background.
2.  **Tonal Transitions:** Using `surface-container-highest` to draw the eye to high-priority data points.

### Surface Hierarchy & Nesting
Think of the UI as layers of fine vellum paper. 
*   **Base Layer:** `surface` (#f5f6f7) for the global background.
*   **Content Areas:** Use `surface-container-low` (#eff1f2) for large content blocks.
*   **Active Interaction Cards:** Use `surface-container-lowest` (#ffffff) to provide the highest contrast against the background, creating a natural "pop."

### The "Glass & Gradient" Rule
To elevate the "Soft Pastel Yellow" (`primary`), do not simply use flat hex codes. 
*   **Floating Elements:** Use `surface-container-lowest` with a 70% opacity and a `backdrop-blur` of 20px for modals or navigation overlays.
*   **Signature CTAs:** Apply a subtle linear gradient from `primary` (#705900) to `primary-container` (#fdd34d) at a 135-degree angle. This adds "soul" and a tactile, premium finish to main actions.

---

### 3. Typography
We use a dual-font system to balance editorial personality with functional readability.

*   **Display & Headlines (Manrope):** The high x-height and geometric curves of Manrope provide a modern, friendly, yet authoritative voice. Use `display-lg` for total balance summaries to make numbers feel like art.
*   **Title & Body (Inter):** Inter is our workhorse. It provides unmatched legibility for the dense data of subscription lists and billing dates.
*   **The Hierarchy Rule:** Always pair a `headline-md` (Manrope) with `body-sm` (Inter) in `on-surface-variant` to create a clear "Title-to-Caption" relationship that guides the user’s eye through complex financial data.

---

## 4. Elevation & Depth
In this design system, depth is felt, not seen. 

*   **The Layering Principle:** Avoid shadows for static cards. Instead, nest a `surface-container-lowest` (#ffffff) card inside a `surface-container` (#e6e8ea) section. The color shift provides all the "elevation" needed.
*   **Ambient Shadows:** For "Floating" elements (e.g., an active subscription edit drawer), use a shadow with a 40px blur and 4% opacity, using the `on-surface` color (#2c2f30) as the shadow tint. It should look like a soft glow of light, not a dark smudge.
*   **The "Ghost Border" Fallback:** If accessibility requires a container boundary, use a "Ghost Border": `outline-variant` at 15% opacity. Never use 100% opaque outlines.
*   **Glassmorphism:** Navigation bars should use the `surface` color at 80% opacity with a heavy blur, allowing the subscription brand colors to bleed through as the user scrolls, maintaining a sense of place.

---

## 5. Components

### Cards & Lists (The Core Experience)
*   **Rule:** Forbid divider lines. 
*   **Implementation:** Use a `spacing-4` (1.4rem) vertical gap between list items. Use a subtle background hover state of `surface-container-high` to indicate interactivity.
*   **Subscription Cards:** Use `surface-container-lowest` with a `lg` (1rem) corner radius. Place the brand icon in the leading position, followed by `title-md` and `body-sm`.

### Buttons
*   **Primary:** Gradient of `primary` to `primary-container`. `full` roundedness. No border. Text is `on-primary-fixed` (#463600).
*   **Secondary:** `surface-container-highest` background with `on-surface` text. This provides a "tactile" feel without the weight of a primary button.
*   **Tertiary:** Text-only using `primary` (#705900), bold weight.

### Form Elements
*   **Inputs:** Utilize `surface-container-low` as the field background. On focus, transition the background to `surface-container-lowest` and add a 2px "Ghost Border" of the `primary` color.
*   **Status Badges:** Use `secondary-container` for "Active" and `error-container` for "Canceled." Keep text in `on-secondary-container` or `on-error-container` for high-contrast legibility.

### Specialized Components
*   **The "Burn Rate" Gauge:** A custom visualization using a `primary-fixed-dim` track and a `primary` indicator to show monthly spend progress.
*   **Micro-Summary Chips:** Small, `md` rounded chips using `tertiary-container` to highlight "Next Billing: June 12."

---

## 6. Do’s and Don’ts

### Do
*   **Do** use `spacing-8` and `spacing-10` for page margins to ensure the "data-heavy" layout doesn't feel suffocating.
*   **Do** use the `rounded-xl` (1.5rem) setting for main dashboard containers to emphasize the "friendly" brand personality.
*   **Do** use the `on-surface-variant` color (#595c5d) for secondary labels to create a sophisticated, muted contrast.

### Don’t
*   **Don't** use pure black (#000000) for text. Use `on-background` (#2c2f30) to maintain a soft, premium feel.
*   **Don't** use 90-degree corners. Everything must have at least a `sm` (0.25rem) radius to stay "friendly."
*   **Don't** use standard "Success" green. Use the `tertiary` (#596000) yellow-green scale for a more custom, branded feel that aligns with the "Subly" yellow.
*   **Don't** crowd the layout. If you think there’s enough white space, add `spacing-2` more.

---
**Director's Note:** This design system is about the *absence* of clutter. Your job is to curate the information, not just display it. Use the yellow sparingly—like a highlighter—to guide the user to their most important financial decisions.