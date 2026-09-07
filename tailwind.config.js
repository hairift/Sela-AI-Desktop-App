/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        sela: {
          50: '#f0f5ff',
          100: '#e0eaff',
          200: '#c7d9ff',
          300: '#a4bfff',
          400: '#7c9fff',
          500: '#5a7fff',
          600: '#3a5ff0',
          700: '#2a4ad0',
          800: '#1e3aaa',
          900: '#162d85',
        },
      },
      keyframes: {
        waveBar: {
          '0%, 100%': { transform: 'scaleY(0.3)' },
          '50%': { transform: 'scaleY(1)' },
        },
        slideInLeft: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
      animation: {
        'wave-1': 'waveBar 1s ease-in-out infinite 0s',
        'wave-2': 'waveBar 1s ease-in-out infinite 0.15s',
        'wave-3': 'waveBar 1s ease-in-out infinite 0.3s',
        'wave-4': 'waveBar 1s ease-in-out infinite 0.45s',
        'wave-5': 'waveBar 1s ease-in-out infinite 0.6s',
        'slide-in-left': 'slideInLeft 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        'fade-in': 'fadeIn 0.4s ease-out',
      },
    },
  },
  plugins: [],
}
