import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      colors: {
        // Дизайн «МедЦена» (Claude Design): тёплая зелёная гамма #0F8A7E.
        brand: {
          50: "#E3F1EE",
          100: "#C9E7E0",
          200: "#A9D8CF",
          300: "#7FC3B7",
          400: "#3FA99B",
          500: "#168E81",
          600: "#0F8A7E",
          700: "#0B6F66",
          800: "#095850",
          900: "#08463F",
          950: "#042925",
        },
        // Тёплый зелёно-серый «чернильный» (текст/границы/фон).
        ink: {
          50: "#F1F5F3",
          100: "#EEF2F0",
          200: "#E4EAE7",
          300: "#C2CDC8",
          400: "#9AA8A2",
          500: "#6A7A73",
          600: "#57655F",
          700: "#3E4D47",
          800: "#28352F",
          900: "#16241F",
          950: "#0C1512",
        },
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(16 80 70 / 0.04), 0 6px 22px -10px rgb(16 80 70 / 0.12)",
        "card-hover": "0 14px 34px -16px rgb(16 80 70 / 0.28)",
        glow: "0 8px 30px -12px rgb(16 80 70 / 0.32)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
        "3xl": "1.75rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
