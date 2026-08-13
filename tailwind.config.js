/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Sora", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      colors: {
        ink: {
          950: "#0F1117",
          900: "#161923",
          800: "#1E2230",
          700: "#2A2F41",
          600: "#3B4155",
        },
        mist: {
          50: "#F6F7FA",
          100: "#EEF0F5",
          200: "#E3E6EE",
          300: "#CBD0DD",
        },
        signal: {
          400: "#8B7CFA",
          500: "#7C6FF0",
          600: "#6656E8",
        },
        pulse: {
          400: "#31E7C4",
          500: "#22D3B8",
        },
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15, 17, 23, 0.04), 0 8px 24px rgba(15, 17, 23, 0.06)",
        bubble: "0 1px 1px rgba(15, 17, 23, 0.04)",
      },
      keyframes: {
        "dot-bounce": {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.4" },
          "40%": { transform: "translateY(-4px)", opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "dot-bounce": "dot-bounce 1.2s infinite ease-in-out",
        "slide-up": "slide-up 0.22s ease-out",
      },
    },
  },
  plugins: [],
};
