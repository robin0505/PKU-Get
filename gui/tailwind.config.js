/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'cyber-black': '#0f172a', // 深邃黑
        'cyber-gray': '#1e293b',  // 科技灰
        'neon-blue': '#3b82f6',   // 霓虹蓝
        'neon-purple': '#8b5cf6', // 赛博紫
        'glass-white': 'rgba(255, 255, 255, 0.1)', // 磨砂玻璃白
      },
      backdropBlur: {
        'xs': '2px',
      }
    },
  },
  plugins: [],
}