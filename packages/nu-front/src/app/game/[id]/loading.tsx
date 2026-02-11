export default function GameLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-felt-green">
      <div className="flex flex-col items-center gap-4">
        <div className="h-6 w-32 animate-pulse rounded bg-white/10" />
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-2 w-2 rounded-full bg-[#d4a843]"
              style={{
                opacity: 0.3,
                animation: "dot-pulse 1.4s ease-in-out infinite",
                animationDelay: `${i * 0.2}s`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
