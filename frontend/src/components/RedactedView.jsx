import { useEffect, useRef } from 'react'
import './RedactedView.css'

function RedactedView({ sseEvents, isVisible }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      const el = scrollRef.current
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 2
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [sseEvents])

  const relevantEvents = sseEvents.filter(e =>
    ['deidentified_query', 'cloud_thinking', 'gatekeeper_query', 'gatekeeper_response', 'web_search_query'].includes(e.type)
  )

  const renderWithTokens = (text) => {
    if (!text) return null
    const tokenPattern = /(\[[A-Z]+_\d+\])/g
    const parts = text.split(tokenPattern)
    return parts.map((part, index) => {
      if (part.match(tokenPattern)) {
        let tokenClass = 'tok-default'
        if (part.includes('PATIENT')) tokenClass = 'tok-patient'
        else if (part.includes('PROVIDER')) tokenClass = 'tok-provider'
        else if (part.includes('DATE')) tokenClass = 'tok-date'
        else if (part.includes('REF')) tokenClass = 'tok-ref'
        else if (part.includes('MRN')) tokenClass = 'tok-mrn'
        else if (part.includes('LOCATION')) tokenClass = 'tok-location'
        return <span key={index} className={`tok ${tokenClass}`}>{part}</span>
      }
      return <span key={index}>{part}</span>
    })
  }

  const getLogPrefix = (type, turn) => {
    switch (type) {
      case 'deidentified_query':
        return { prefix: '[GATEKEEPER → CLOUD]', cls: 'log-gatekeeper' }
      case 'cloud_thinking':
        return { prefix: '[CLOUD]', cls: 'log-cloud' }
      case 'gatekeeper_query':
        return { prefix: `[CLOUD → GATEKEEPER] turn=${turn || '?'}`, cls: 'log-cloud' }
      case 'gatekeeper_response':
        return { prefix: `[GATEKEEPER → CLOUD] turn=${turn || '?'}`, cls: 'log-gatekeeper' }
      case 'web_search_query':
        return { prefix: `[CLOUD → WEB] turn=${turn || '?'}`, cls: 'log-cloud' }
      default:
        return { prefix: `[${type}]`, cls: 'log-default' }
    }
  }

  if (!isVisible) return null

  return (
    <div className="term-pipeline">
      <div className="term-header">
        <span className="term-dot term-dot-red"></span>
        <span className="term-dot term-dot-yellow"></span>
        <span className="term-dot term-dot-green"></span>
        <span className="term-title">phi-pipeline</span>
      </div>
      <div className="term-body" ref={scrollRef}>
        {relevantEvents.length === 0 ? (
          <div className="term-line term-muted">
            <span className="term-prompt">$</span> waiting for query...
          </div>
        ) : (
          relevantEvents.map((event, i) => {
            const { prefix, cls } = getLogPrefix(event.type, event.turn)
            return (
              <div key={i} className="term-line">
                <span className={`term-prefix ${cls}`}>{prefix}</span>
                <span className="term-content">{renderWithTokens(event.content)}</span>
                {event.token_summary && (
                  <div className="term-tokens">
                    <span className="term-muted">  tokens: </span>
                    {Object.entries(event.token_summary).map(([token, type]) => (
                      <span key={token} className="term-muted">{token}={type} </span>
                    ))}
                  </div>
                )}
                {event.refs_added && event.refs_added.length > 0 && (
                  <div className="term-tokens">
                    <span className="term-muted">  refs: {event.refs_added.join(', ')}</span>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default RedactedView
