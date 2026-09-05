/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Base surfaces — deep oceanic slate navy, ECDIS S-52 night palette.
        "chart-abyss": "#060B11",
        "chart-surface": "#0A121C",
        "chart-raised": "#0F1926",
        "chart-hover": "#152334",
        "chart-contour": "#1D2E42",

        // Typography ink.
        "ink-primary": "#E6EDF3",
        "ink-secondary": "#8D9EA8",
        "ink-tertiary": "#526573",

        // Provenance badges — per-source data lineage, never a global disclaimer.
        "prov-gfw": "#2DD4BF",
        "prov-aisstream": "#38BDF8",
        "prov-synthetic": "#927B56",

        // Status signals.
        "signal-attention": "#F59E0B",
        "signal-alert": "#DC2626",
        "signal-positive": "#10B981",
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        serif: ["'Spectral'", "Georgia", "serif"],
      },
      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "2px",
      },
    },
  },
  plugins: [],
};
