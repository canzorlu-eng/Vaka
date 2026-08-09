/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        head: ['Nunito', 'sans-serif'],
        body: ['Figtree', 'sans-serif'],
      },
      colors: {
        bg: 'var(--bg)',
        fg: 'var(--fg)',
        card: 'var(--card)',
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-fg)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-fg)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-fg)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-fg)' },
        border: 'var(--border)',
        ring: 'var(--ring)',
        peach: '#FF937B',
        cream: '#FDFBF7',
        sage: '#82C3A6',
        clay: '#5C4A3D',
      },
      borderRadius: {
        xl: '18px',
        '2xl': '24px',
        '3xl': '28px',
      },
    },
  },
  plugins: [],
};
