// Animated voice orb reacting to call state.
// listening = blue pulsing rings, thinking = amber rotating,
// speaking = green animated bars, idle = gray.
export default function VoiceOrb({ state = 'idle', size = 180 }) {
  const bars = [0.9, 0.6, 1.0, 0.7, 1.1, 0.8, 1.0, 0.6]
  return (
    <div className={`orb orb-${state}`} style={{ width: size, height: size }} aria-label={`call state: ${state}`}>
      <div className="orb-ring orb-ring-1" />
      <div className="orb-ring orb-ring-2" />
      <div className="orb-core">
        {state === 'speaking' ? (
          <div className="orb-bars">
            {bars.map((h, i) => (
              <span
                key={i}
                className="orb-bar"
                style={{ animationDelay: `${i * 0.12}s`, ['--bh']: `${Math.round(h * 100)}%` }}
              />
            ))}
          </div>
        ) : state === 'thinking' ? (
          <div className="orb-spinner" />
        ) : (
          <div className="orb-dot" />
        )}
      </div>
    </div>
  )
}
