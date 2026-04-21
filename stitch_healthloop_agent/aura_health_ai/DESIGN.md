# Design System Specification: The Clinical Precision Framework

## 1. Overview & Creative North Star
The North Star for this design system is **"The Digital Clinician."** 

In the medical AI space, trust is not built through decoration, but through extreme clarity, intentionality, and a sense of "quiet authority." This system moves away from the cluttered, dashboard-heavy aesthetics of legacy medical software. Instead, it adopts a **High-End Editorial** approach—treating patient data and AI insights as precious content. 

We break the "template" look by utilizing **Tonal Layering** and **Intentional Asymmetry**. By placing high-density data visualization against vast areas of `surface` whitespace, we create a rhythm that guides the clinician's eye to what matters most. The design feels like a bespoke medical journal—authoritative, clean, and vital.

---

## 2. Colors & Surface Architecture

### The Palette
We utilize a sophisticated Material-based palette centered around medical precision.
- **Primary (`#0040e0`):** Our "Trust Anchor." Used for core actions and primary navigation highlights.
- **Secondary (`#006a62`):** Representing "Vitality." Used for success states, health metrics, and positive diagnostic outcomes.
- **Tertiary (`#704f00`):** An "Observational Amber." Used for low-priority warnings that require attention without inducing panic.

### The "No-Line" Rule
To achieve a premium, modern feel, **this design system prohibits 1px solid borders for sectioning.** 
*   **The Mandate:** Boundaries must be defined solely through background color shifts. For example, a `surface-container-low` side panel sitting on a `surface` main canvas. 
*   **The Goal:** Eliminate visual noise (lines) to allow the content to breathe.

### Surface Hierarchy & Nesting
Treat the UI as physical layers of "Medical Glass."
*   **Base Layer:** `surface` (#f7f9fb)
*   **Sectioning:** Use `surface-container-low` (#f2f4f6) for large layout blocks.
*   **Focus Areas:** Use `surface-container-lowest` (#ffffff) for the most critical cards or data entries. This creates a "lift" effect where the most important information is physically closer to the user.

### The "Glass & Gradient" Rule
For floating AI-assistant panels or "Inquiry Zone" overlays, use **Glassmorphism**:
*   **Style:** `surface` color at 70% opacity + 20px Backdrop Blur.
*   **Gradients:** Use a subtle linear gradient (Top-Left to Bottom-Right) from `primary` (#0040e0) to `primary-container` (#2e5bff) for high-impact CTAs to give them a "holographic" depth that feels advanced and AI-driven.

---

## 3. Typography: The Editorial Voice

We utilize a dual-typeface system to balance clinical authority with modern efficiency.

*   **Display & Headlines (Manrope):** A geometric sans-serif with an approachable yet technical personality.
    *   *Usage:* Used for patient names, diagnostic titles, and high-level platform sections. It signals a premium, curated experience.
*   **Body & Labels (Inter):** The workhorse. Chosen for its exceptional legibility in high-density medical data.
    *   *Usage:* Used for all clinical notes, lab values, and platform instructions.

**Key Scales:**
- **Display-LG (3.5rem / Manrope):** Use sparingly for hero data points (e.g., a critical health score).
- **Title-MD (1.125rem / Inter):** The standard for card headers.
- **Label-SM (0.6875rem / Inter):** For metadata, ensuring it remains present but doesn't compete with primary clinical data.

---

## 4. Elevation & Depth: The Layering Principle

### Tonal Layering
Traditional shadows are replaced by **Tonal Stacking**. 
*   Place a `surface-container-lowest` card on top of a `surface-container` background. The contrast between white and soft grey provides all the separation needed without adding "ink" to the screen.

### Ambient Shadows
When an element must float (e.g., a diagnostic popover):
*   **Shadow:** `on-surface` color at 6% opacity.
*   **Blur:** 32px to 48px.
*   **Offset:** 8px Y-axis.
*   **Result:** A soft, ambient glow that feels like natural light in a clean clinical environment.

### The "Ghost Border" Fallback
If contrast testing fails for accessibility:
*   **Rule:** Use `outline-variant` at **15% opacity**. It should be felt, not seen.

---

## 5. Components & Workspace Differentiation

### Workspace Zones
To prevent clinical errors, the system utilizes **Environmental Tints**:
*   **Inquiry Zone (Search/Research):** Background uses `surface` (#f7f9fb).
*   **Execution Zone (Prescribing/Action):** Header shifts to a subtle `primary-fixed` (#dde1ff) tint to signal "Active Mode."

### Buttons
*   **Primary:** Solid `primary` with `on-primary` text. No border. `xl` roundedness (0.75rem).
*   **Secondary:** `primary-container` background with `on-primary-container` text.
*   **Tertiary:** Transparent background with `primary` text. Use only for "Cancel" or "Back" actions.

### Cards & Lists
*   **Strict Rule:** No dividers. 
*   **Separation:** Use 24px (1.5rem) vertical spacing between list items. Use a `surface-variant` background on hover to indicate interactivity.
*   **Corner Radius:** Cards use `xl` (0.75rem) for a soft, approachable feel. Small components like chips use `full` (9999px).

### Input Fields
*   **Style:** Minimalist. No bottom line. Use `surface-container-high` as the background.
*   **Focus State:** A 2px "Ghost Border" of `primary` at 40% opacity.

---

## 6. Do’s and Don’ts

### Do
*   **DO** use whitespace as a functional tool to reduce clinician cognitive load.
*   **DO** use `secondary` (Teal) for all "Normal" lab results to provide instant visual reassurance.
*   **DO** overlap elements slightly (e.g., a floating action button overlapping a card edge) to create a sense of depth and custom UI.

### Don't
*   **DON'T** use pure black (#000000). Always use `on-surface` (#191c1e) for text to maintain a soft, high-end look.
*   **DON'T** use 100% opaque borders. They create "visual cages" that make the software feel dated.
*   **DON'T** use standard "drop shadows." If the shadow looks like a shadow, it’s too dark. It should look like a "soft lift."

### Accessibility Note
While we prioritize a "No-Line" aesthetic, always ensure the contrast between `surface` and `surface-container` tiers meets WCAG AA standards for essential UI boundaries.