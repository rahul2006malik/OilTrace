/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        space: {
          dark: '#070a13',
          darker: '#04060c',
          panel: '#0c1222',
          surface: '#111827',
          card: '#0f172a',
          hover: '#1e293b',
          border: '#1e293b',
          borderLight: '#334155',
        },
        radar: {
          cyan: '#06b6d4',
          cyanDim: '#0891b2',
          cyanGlow: 'rgba(6, 182, 212, 0.25)',
        },
        origin: {
          gold: '#f59e0b',
          goldDim: '#d97706',
          orange: '#f97316',
        },
        tactical: {
          emerald: '#10b981',
          crimson: '#ef4444',
          violet: '#a855f7',
          sky: '#38bdf8',
          amber: '#f59e0b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'radar-sweep': 'sweep 4s linear infinite',
      },
      keyframes: {
        sweep: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        }
      }
    },
  },
  plugins: [],
}
