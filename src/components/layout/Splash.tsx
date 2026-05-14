import logo from '@/assets/logo-alos.svg'

interface SplashProps {
  message?: string
  subtext?: string
}

/**
 * Shown while the Python backend is booting (first 5-15s of app start).
 * Also used as a fallback when the backend goes offline.
 */
export function Splash({ message = 'Starting ALOS…', subtext }: SplashProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-background">
      <div className="relative">
        <img
          src={logo}
          alt="ALOS"
          className="h-28 w-28 animate-pulse-soft"
          style={{ color: 'var(--color-primary)' }}
        />
      </div>
      <h1 className="mt-8 text-2xl font-semibold tracking-tight">ALOS</h1>
      <p className="mt-3 text-sm text-muted-foreground">{message}</p>
      {subtext && (
        <p className="mt-1 text-xs text-muted-foreground/70">{subtext}</p>
      )}

      <style>{`
        @keyframes pulse-soft {
          0%, 100% { opacity: 1; filter: drop-shadow(0 0 8px hsl(184 100% 50% / 0.3)); }
          50%      { opacity: 0.7; filter: drop-shadow(0 0 24px hsl(184 100% 50% / 0.6)); }
        }
        .animate-pulse-soft { animation: pulse-soft 2.4s ease-in-out infinite; }
      `}</style>
    </div>
  )
}
