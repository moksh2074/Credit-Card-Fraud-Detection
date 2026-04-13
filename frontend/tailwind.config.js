// frontend/tailwind.config.js
export default {
    content: ['./index.html', './src/**/*.{js,jsx}'],
    theme: {
        extend: {
            colors: {
                primary: {
                    DEFAULT: '#6366F1',
                    dark: '#4F46E5',
                    light: '#818CF8',
                    muted: 'rgba(99,102,241,0.15)',
                    subtle: 'rgba(99,102,241,0.08)',
                },
                alert: {
                    DEFAULT: '#EF4444',
                    dark: '#DC2626',
                    light: '#F87171',
                    muted: 'rgba(239,68,68,0.15)',
                    subtle: 'rgba(239,68,68,0.08)',
                },
                success: { DEFAULT: '#10B981', dark: '#059669', light: '#34D399' },
                warning: { DEFAULT: '#F59E0B', dark: '#D97706', light: '#FCD34D' },
                danger: { DEFAULT: '#F97316', dark: '#EA580C', light: '#FB923C' },
                info: { DEFAULT: '#38BDF8', dark: '#0EA5E9', light: '#7DD3FC' },
                surface: {
                    base: '#0B0F1A',
                    card: '#111827',
                    elevated: '#1A2236',
                    input: '#0D1321',
                    glass: 'rgba(17,24,39,0.6)',
                },
                text: {
                    primary: '#F1F5F9',
                    secondary: '#94A3B8',
                    muted: '#64748B',
                },
                border: {
                    DEFAULT: '#1E293B',
                    subtle: '#0F172A',
                },
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
                mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
            },
            borderRadius: {
                sm: '6px',
                md: '10px',
                lg: '14px',
                xl: '20px',
                '2xl': '28px',
            },
            boxShadow: {
                'card': '0 4px 16px rgba(0,0,0,0.55)',
                'card-lg': '0 8px 32px rgba(0,0,0,0.6)',
                'glow-primary': '0 0 20px rgba(99,102,241,0.3)',
                'glow-alert': '0 0 20px rgba(239,68,68,0.3)',
                'glow-success': '0 0 16px rgba(16,185,129,0.25)',
            },
        },
    },
    plugins: [],
}