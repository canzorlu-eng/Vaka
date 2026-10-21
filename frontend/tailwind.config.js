/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        head: ['Fraunces', 'Georgia', 'serif'],
        body: ['Figtree', 'sans-serif'],
      },
      colors: {
        bg: 'var(--bg)',
        fg: 'var(--fg)',
        card: { DEFAULT: 'var(--card)', foreground: 'var(--fg)' },
        // shadcn/ui primitives (menus, dialogs) reference these semantic names
        background: 'var(--bg)',
        foreground: 'var(--fg)',
        popover: { DEFAULT: 'var(--card)', foreground: 'var(--fg)' },
        destructive: { DEFAULT: 'var(--coral)', foreground: '#FFFFFF' },
        input: 'var(--border)',
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-fg)', soft: 'var(--primary-soft)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-fg)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-fg)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-fg)' },
        border: 'var(--border)',
        ring: 'var(--ring)',
        peach: '#E8896F', coral: { DEFAULT: 'var(--coral)', soft: 'var(--coral-soft)' },
        cream: '#FDFBF7',
        sage: '#82C3A6',
        clay: '#4A4137',
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
