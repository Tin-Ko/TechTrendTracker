/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#121414",
        surface: "#121414",
        "surface-dim": "#121414",
        "surface-bright": "#383939",
        "surface-container-lowest": "#0d0e0f",
        "surface-container-low": "#1b1c1c",
        "surface-container": "#1f2020",
        "surface-container-high": "#292a2a",
        "surface-container-highest": "#343535",
        "surface-variant": "#343535",
        "surface-tint": "#c6c6c7",

        "on-background": "#e3e2e2",
        "on-surface": "#e3e2e2",
        "on-surface-variant": "#c4c7c8",
        "inverse-surface": "#e3e2e2",
        "inverse-on-surface": "#303031",

        outline: "#8e9192",
        "outline-variant": "#444748",

        primary: "#ffffff",
        "on-primary": "#2f3131",
        "primary-container": "#e2e2e2",
        "on-primary-container": "#636565",
        "inverse-primary": "#5d5f5f",

        secondary: "#c8c6c5",
        "on-secondary": "#313030",
        "secondary-container": "#4a4949",
        "on-secondary-container": "#bab8b7",

        tertiary: "#ffffff",
        "on-tertiary": "#2f3131",
        "tertiary-container": "#e2e2e2",
        "on-tertiary-container": "#636565",

        error: "#ffb4ab",
        "on-error": "#690005",
        "error-container": "#93000a",
        "on-error-container": "#ffdad6",
      },
      borderRadius: {
        DEFAULT: "1rem",
        sm: "0.5rem",
        md: "1.5rem",
        lg: "2rem",
        xl: "3rem",
        full: "9999px",
      },
      spacing: {
        "section-gap": "4rem",
        "inner-gutter": "1rem",
        "component-padding": "1.25rem",
      },
      maxWidth: {
        "container-max": "800px",
      },
      fontFamily: {
        "display-lg": ["Geist", "sans-serif"],
        "display-lg-mobile": ["Geist", "sans-serif"],
        "headline-md": ["Geist", "sans-serif"],
        "body-lg": ["Geist", "sans-serif"],
        "label-md": ["Geist", "sans-serif"],
      },
      fontSize: {
        "display-lg": ["120px", { lineHeight: "110%", letterSpacing: "-0.05em", fontWeight: "800" }],
        "display-lg-mobile": ["64px", { lineHeight: "110%", fontWeight: "800" }],
        "headline-md": ["32px", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        "body-lg": ["18px", { lineHeight: "1.6", letterSpacing: "0", fontWeight: "400" }],
        "label-md": ["14px", { lineHeight: "1.2", letterSpacing: "0.05em", fontWeight: "500" }],
      },
    },
  },
  plugins: [],
};
