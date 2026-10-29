const c = (n) => `rgb(var(--${n}) / <alpha-value>)`;
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: c("bg"), surface: c("surface"), "surface-2": c("surface-2"), line: c("line"),
        fg: c("fg"), muted: c("muted"), accent: c("accent"), "accent-fg": c("accent-fg"),
        ok: c("ok"), warn: c("warn"), danger: c("danger"),
      },
      fontFamily: { sans: ['"Inter Variable"', "ui-sans-serif", "system-ui", "sans-serif"] },
      borderRadius: { DEFAULT: "0.5rem", lg: "0.75rem" },
      boxShadow: { card: "0 1px 2px rgb(0 0 0 / 0.12), 0 0 0 1px rgb(var(--line) / 1)" },
    },
  },
  plugins: [],
};
