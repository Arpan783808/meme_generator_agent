/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'terminal-green': '#00ff41',
        'space-black': '#0a0b10',
        'terminal-green-dim': 'rgba(0, 255, 65, 0.5)',
        'terminal-bg': 'rgba(10, 11, 16, 0.4)',
      },
      fontFamily: {
        mono: ['"Courier New"', 'Courier', 'monospace'],
      },
      animation: {
        'spin-slow': 'spin-slow 240s linear infinite',
        'blink': 'blink 1s step-end infinite',
      },
      keyframes: {
        'spin-slow': {
          'from': { transform: 'rotate(0deg)' },
          'to': { transform: 'rotate(360deg)' },
        },
        'blink': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        }
      }
    },
  },
  plugins: [
    require('tailwind-scrollbar'),
  ],
}
