/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/**/*.py"],
  darkMode: "class", // light theme only
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#b3121e",       // primary buttons, active tab, eyebrows, focus, selection
          redhover: "#8f0e18",  // hover of every red button
          ink: "#14181f",       // headings and body text
          cream: "#fbf9f6",     // page background
          muted: "#5b6270",     // secondary text
          tile: "#e8edf6",      // chips, tiles, Admin badge background
          navy: "#26405c",      // Admin badge text
        },
      },
      borderRadius: { lg: "8px", xl: "10px", "2xl": "10px", "3xl": "10px" }, // fields 8px, cards and buttons 10px
      fontFamily: {
        display: ['"Manrope"', "system-ui", "sans-serif"],
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
      },
    },
  },
};
