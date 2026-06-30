---
name: Ultra-Minimalist Search
colors:
  surface: '#121414'
  surface-dim: '#121414'
  surface-bright: '#383939'
  surface-container-lowest: '#0d0e0f'
  surface-container-low: '#1b1c1c'
  surface-container: '#1f2020'
  surface-container-high: '#292a2a'
  surface-container-highest: '#343535'
  on-surface: '#e3e2e2'
  on-surface-variant: '#c4c7c8'
  inverse-surface: '#e3e2e2'
  inverse-on-surface: '#303031'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c6c6c7'
  primary: '#ffffff'
  on-primary: '#2f3131'
  primary-container: '#e2e2e2'
  on-primary-container: '#636565'
  inverse-primary: '#5d5f5f'
  secondary: '#c8c6c5'
  on-secondary: '#313030'
  secondary-container: '#4a4949'
  on-secondary-container: '#bab8b7'
  tertiary: '#ffffff'
  on-tertiary: '#2f3131'
  tertiary-container: '#e2e2e2'
  on-tertiary-container: '#636565'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c7'
  on-primary-fixed: '#1a1c1c'
  on-primary-fixed-variant: '#454747'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474646'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c7'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#121414'
  on-background: '#e3e2e2'
  surface-variant: '#343535'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 120px
    fontWeight: '800'
    lineHeight: 110%
    letterSpacing: -0.05em
  headline-md:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: 0.05em
  display-lg-mobile:
    fontFamily: Geist
    fontSize: 64px
    fontWeight: '800'
    lineHeight: 110%
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  container-max-width: 800px
  section-gap: 4rem
  component-padding: 1.25rem
  inner-gutter: 1rem
---

## Brand & Style
The design system embodies a hyper-focused, minimalist aesthetic designed for maximum efficiency and clarity. It targets a sophisticated audience that values speed and precision. By removing all peripheral navigation, the UI creates a singular "flow state" focused entirely on the search action. The visual style leverages **Minimalism** with a touch of **Glassmorphism** for depth, using a monochromatic palette to convey authority and modern technical precision. The emotional response is one of calm, professional focus.

## Colors
The color palette is strictly monochromatic to ensure zero distractions. 
- **Background:** A deep, radial or linear gradient from #0e0e0e to #131313 provides a sense of infinite space.
- **Primary:** Pure White (#FFFFFF) is reserved for high-contrast interaction points, active text, and primary icons.
- **Secondary/Surface:** Deep greys and semi-transparent whites are used for container borders and inactive states.
- **Neutral:** Mid-tone greys (#888888) are used for placeholder text and secondary information to maintain a clear visual hierarchy.

## Typography
This design system uses **Geist** for its technical precision and clean, developer-friendly proportions. The hierarchy is extreme: the "TTT" branding acts as a massive display anchor, while all other text is scaled down to maintain the central focus.
- **Display:** Used for the TTT logo, utilizing heavy weights and tight tracking for a block-like, architectural feel.
- **Body:** Sized for optimal readability within the search bar, using a regular weight to contrast against the bold branding.
- **Labels:** Used for micro-copy or secondary metadata, often using increased letter spacing for an editorial look.

## Layout & Spacing
The layout follows a **Strictly Centered** philosophy. All elements are vertically and horizontally aligned to the center of the viewport to create a balanced, zen-like interface. 

- **Desktop:** Elements are constrained to a narrow central column (max 800px) to prevent eye strain across ultra-wide monitors.
- **Mobile:** Margins expand to 24px, and the display typography scales down significantly to ensure the pill-shaped search bar remains the dominant focal point.
- **Rhythm:** Vertical spacing between the logo and the search bar uses a consistent 4rem (64px) gap to provide breathing room.

## Elevation & Depth
Depth is created through subtle **Tonal Layers** and **Ambient Shadows** rather than traditional elevation.
- **Logo Depth:** The central "TTT" branding utilizes a soft, diffused drop shadow with high blur and low opacity to lift it off the gradient background.
- **Container Blurs:** The search pill uses a very thin (1px) semi-transparent border and a subtle backdrop blur (10px - 20px) to feel like a lens resting on the surface.
- **Interaction Glow:** Active states should utilize a soft outer glow rather than a hard shadow to maintain the "digital neon" minimalist aesthetic.

## Shapes
The shape language is defined by the **Pill-shape** (fully rounded corners). This softens the starkness of the dark mode and creates a container that feels modern and approachable.
- **Search Bar:** Always uses `rounded-full` (pill) styling.
- **Action Buttons:** Small circular buttons (like the search arrow) contrast against the elongated horizontal pill.
- **Branding:** The logo remains geometric and sharp, providing a visual counterpoint to the rounded interface elements.

## Components
### Search Bar
The primary component is a pill-shaped input. It features a thin 1px border (#FFFFFF at 20% opacity). The placeholder text is centered or left-aligned depending on state, using Geist Regular at #888888.

### Action Icons
Buttons within inputs (like the submit arrow) are contained within a white circular background. The icon itself is knocked out in the background color (#131313) for maximum contrast.

### Input Fields
Inputs are border-only by default. Upon focus, the border opacity increases to 100% white, and a very subtle inner shadow is applied to give a sense of depression into the surface.

### Branding (TTT)
The branding is treated as a component. It uses a gradient fill or high-contrast white with a subtle "long shadow" or diffused glow to maintain legibility against the dark background.
