# AI DevOS — Frontend Design Specification (DESIGN_SPEC.md)

## Product Identity & Core User Journeys

### Product Identity
- **Name**: AI DevOS Generated Platform
- **Target Users**: Multi-role applications (Customer, Merchant/Vendor, Admin, Operations)
- **Visual Personality**: Modern, friction-free, high-legibility interface using dark/light theme tokens.

---

## 1. Information Architecture & Navigation

```
App Shell / Navigation Bar
├── Dashboard / Home Screen
├── Discovery & Search View
├── Details / Management View
├── Transaction & Checkout Flow
└── Settings & Profile
```

---

## 2. Design System Tokens

### Typography
- **Primary Font**: `Inter`, sans-serif (Google Fonts)
- **Monospace Font**: `JetBrains Mono` (Code & Data view)
- **Hierarchy**:
  - `h1`: 2.25rem (36px), font-weight: 700, tracking: -0.025em
  - `h2`: 1.75rem (28px), font-weight: 600
  - `h3`: 1.25rem (20px), font-weight: 600
  - `body-lg`: 1.125rem (18px)
  - `body-md`: 1rem (16px), line-height: 1.5
  - `caption`: 0.75rem (12px), text-muted

### Color Palette (HSL Design Tokens)
- **Background**: `hsl(240, 10%, 4%)` (Dark) / `hsl(0, 0%, 100%)` (Light)
- **Surface / Card**: `hsl(240, 6%, 10%)`
- **Primary Accent**: `hsl(217, 91%, 60%)` (Blue)
- **Secondary Accent**: `hsl(142, 71%, 45%)` (Emerald Green)
- **Destructive**: `hsl(0, 84%, 60%)` (Red)
- **Border**: `hsl(240, 5%, 18%)`

### Spacing & Grid System
- **Base Unit**: 4px (8px, 12px, 16px, 24px, 32px, 48px, 64px)
- **Breakpoints**:
  - `sm`: 640px (Mobile portrait)
  - `md`: 768px (Tablet / Mobile landscape)
  - `lg`: 1024px (Laptop)
  - `xl`: 1280px (Desktop)

---

## 3. Component State Inventory

Every generated component MUST implement 8 explicit interaction states:

1. **Default**: Initial render state.
2. **Hover**: Smooth micro-transition on interactive elements (`transition-all duration-200`).
3. **Active / Pressed**: Subtle inset visual cue (`scale-[0.98]`).
4. **Disabled**: Reduced opacity (`opacity-50 pointer-events-none`).
5. **Loading**: Skeleton placeholder or inline spinner animation (`animate-pulse`).
6. **Empty**: Clear icon, descriptive feedback, and primary action button.
7. **Error**: Red accent border, error message text, and retry trigger.
8. **Success**: Toast / banner confirmation with emerald check badge.

---

## 4. Modal, Form & Drawer Behaviors

- **Forms**: Client-side validation prior to submit, inline error messages below invalid fields.
- **Modals**: Focus lock, backdrop blur (`backdrop-blur-sm`), ESC key closure trigger.
- **Drawers**: Slide-over for mobile navigation and detailed inspection panels.

---
*Design Specification — AI DevOS Phase 4*
