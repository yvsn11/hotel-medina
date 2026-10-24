/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        zellige: {
          50: '#EAF4F4',
          100: '#CFE5E6',
          200: '#9FCBCD',
          300: '#6BAEB2',
          400: '#3A8D94',
          500: '#1D6F78',
          600: '#12575F',
          700: '#0D4650',
          800: '#0A353D',
          900: '#07272D',
        },
        terracotta: {
          50: '#FBEFE9',
          100: '#F5D6C8',
          300: '#DE9677',
          500: '#C0603A',
          600: '#A24C2B',
          700: '#833B20',
        },
        sand: {
          50: '#FBF8F2',
          100: '#F5EFE3',
          200: '#EADFCB',
          300: '#DCCCAF',
          400: '#BFA97F',
        },
        brass: { 400: '#C9A24A', 600: '#8A6A1E' },
        ink: { DEFAULT: '#1D2B2E', soft: '#4A5A5D' },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'Cambria', 'serif'],
        sans: ['"Hanken Grotesk"', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 18px 40px -22px rgba(7,39,45,0.55)',
      },
    },
  },
  plugins: [],
};
