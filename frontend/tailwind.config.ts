import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#16213a",
        canvas: "#f5f7fb",
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81"
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 18px 42px rgba(15, 23, 42, 0.06)",
        glow: "0 18px 55px rgba(79, 70, 229, 0.24)",
      },
      animation: {
        "fade-in": "fade-in 420ms ease-out both",
        "slide-up": "slide-up 500ms ease-out both",
        "pulse-soft": "pulse-soft 2.2s ease-in-out infinite",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: ".55" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
