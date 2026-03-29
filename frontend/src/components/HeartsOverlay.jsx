import { useState, useEffect, useCallback } from 'react'
import './HeartsOverlay.css'

// Heart shapes to randomly pick from
const HEART_CHARS = ['♥', '❤', '💕', '💗', '💖', '💘']

function HeartsOverlay({ isActive }) {
  const [hearts, setHearts] = useState([])

  // Spawn a new heart
  const spawnHeart = useCallback(() => {
    const id = Date.now() + Math.random()
    const heart = {
      id,
      char: HEART_CHARS[Math.floor(Math.random() * HEART_CHARS.length)],
      x: Math.random() * 100, // percentage across screen
      size: 16 + Math.random() * 24, // 16-40px
      duration: 3 + Math.random() * 2, // 3-5 seconds
      delay: Math.random() * 0.5,
      drift: (Math.random() - 0.5) * 100, // horizontal drift in px
    }
    setHearts((prev) => [...prev, heart])

    // Remove heart after animation completes
    setTimeout(() => {
      setHearts((prev) => prev.filter((h) => h.id !== id))
    }, (heart.duration + heart.delay) * 1000 + 500)
  }, [])

  // Spawn hearts continuously while active
  useEffect(() => {
    if (!isActive) {
      setHearts([])
      return
    }

    // Initial burst of hearts
    for (let i = 0; i < 8; i++) {
      setTimeout(() => spawnHeart(), i * 100)
    }

    // Continue spawning
    const interval = setInterval(() => {
      spawnHeart()
    }, 200)

    // Stop spawning after 15 seconds, let existing hearts finish
    const stopTimer = setTimeout(() => {
      clearInterval(interval)
    }, 15000)

    return () => {
      clearInterval(interval)
      clearTimeout(stopTimer)
    }
  }, [isActive, spawnHeart])

  if (!isActive && hearts.length === 0) return null

  return (
    <div className="hearts-overlay">
      {hearts.map((heart) => (
        <span
          key={heart.id}
          className="floating-heart"
          style={{
            left: `${heart.x}%`,
            fontSize: `${heart.size}px`,
            '--duration': `${heart.duration}s`,
            '--delay': `${heart.delay}s`,
            '--drift': `${heart.drift}px`,
          }}
        >
          {heart.char}
        </span>
      ))}
    </div>
  )
}

export default HeartsOverlay
