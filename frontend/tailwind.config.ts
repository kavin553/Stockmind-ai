import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark industrial enterprise palette
        base: {
          900: "#0B0F17",
          800: "#101725",
          700: "#161F31",
          600: "#1E293F",
          500: "#2A3A56",
        },
        accent: {
          cyan: "#00F2FE",
          blue: "#4FACFE",
        },
        signal: {
          success: "#10B981",
          warning: "#F59E0B",
          critical: "#EF4444",
          muted: "#64748B",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -6px rgba(0, 242, 254, 0.45)",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
      animation: {
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
