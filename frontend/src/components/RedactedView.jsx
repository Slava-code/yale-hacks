import { useState, useEffect, useRef } from 'react'
import './RedactedView.css'

function RedactedView({ sseEvents, isVisible, onClose }) {
  const eventsEndRef = useRef(null)

  // Auto-scroll to bottom when events change
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [sseEvents])

  // Filter relevant events for the redacted view
  const relevantEvents = sseEvents.filter(e =>
    ['deidentified_query', 'cloud_thinking', 'gatekeeper_query', 'gatekeeper_response'].includes(e.type)
  )

  // Render PHI tokens with highlighting
  const renderWithTokens = (text) => {
    if (!text) return null

    // Match PHI tokens like [PATIENT_1], [REF_1], [DATE_1], etc.
    const tokenPattern = /(\[[A-Z]+_\d+\])/g
    const parts = text.split(tokenPattern)

    return parts.map((part, index) => {
      if (part.match(tokenPattern)) {
        // Determine token type for coloring
        let tokenClass = 'token-default'
        if (part.includes('PATIENT')) tokenClass = 'token-patient'
        else if (part.includes('PROVIDER')) tokenClass = 'token-provider'
        else if (part.includes('DATE')) tokenClass = 'token-date'
        else if (part.includes('REF')) tokenClass = 'token-ref'
        else if (part.includes('MRN')) tokenClass = 'token-mrn'
        else if (part.includes('LOCATION')) tokenClass = 'token-location'

        return (
          <span key={index} className={`redacted-token ${tokenClass}`}>
            {part}
          </span>
        )
      }
      return <span key={index}>{part}</span>
    })
  }

  // Get event icon and label
  const getEventMeta = (type) => {
    switch (type) {
      case 'deidentified_query':
        return { label: 'De-identified Query', icon: '→' }
      case 'cloud_thinking':
        return { label: 'Cloud Model', icon: '◆' }
      case 'gatekeeper_query':
        return { label: 'Gatekeeper Query', icon: '↓' }
      case 'gatekeeper_response':
        return { label: 'Gatekeeper Response', icon: '↑' }
      default:
        return { label: type, icon: '•' }
    }
  }

  if (!isVisible) return null

  return (
    <div className="redacted-view">
      {/* Header */}
      <div className="redacted-header">
        <div className="redacted-title-section">
          <span className="redacted-icon">◈</span>
          <span className="redacted-title">Redacted View</span>
          <span className="redacted-subtitle">What the cloud sees</span>
        </div>
        <button className="redacted-close-btn" onClick={onClose}>
          ×
        </button>
      </div>

      {/* Events List */}
      <div className="redacted-events">
        {relevantEvents.length === 0 ? (
          <div className="redacted-empty">
            <div className="redacted-empty-icon">◈</div>
            <div className="redacted-empty-text">
              Submit a query to see the de-identified conversation
            </div>
          </div>
        ) : (
          <>
            {relevantEvents.map((event, index) => {
              const meta = getEventMeta(event.type)
              return (
                <div key={index} className={`redacted-event redacted-event-${event.type}`}>
                  <div className="redacted-event-header">
                    <span className="redacted-event-icon">{meta.icon}</span>
                    <span className="redacted-event-label">{meta.label}</span>
                    {event.turn && (
                      <span className="redacted-event-turn">Turn {event.turn}</span>
                    )}
                  </div>
                  <div className="redacted-event-content">
                    {renderWithTokens(event.content)}
                  </div>
                  {event.token_summary && (
                    <div className="redacted-token-summary">
                      {Object.entries(event.token_summary).map(([token, type]) => (
                        <span key={token} className="redacted-token-badge">
                          {token}: {type}
                        </span>
                      ))}
                    </div>
                  )}
                  {event.refs_added && event.refs_added.length > 0 && (
                    <div className="redacted-refs-added">
                      <span className="redacted-refs-label">Citations added:</span>
                      {event.refs_added.map(ref => (
                        <span key={ref} className="redacted-ref-badge">{ref}</span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            <div ref={eventsEndRef} />
          </>
        )}
      </div>

      {/* Legend */}
      <div className="redacted-legend">
        <span className="redacted-legend-title">PHI Tokens:</span>
        <span className="redacted-token token-patient">[PATIENT]</span>
        <span className="redacted-token token-provider">[PROVIDER]</span>
        <span className="redacted-token token-date">[DATE]</span>
        <span className="redacted-token token-ref">[REF]</span>
      </div>
    </div>
  )
}

export default RedactedView
