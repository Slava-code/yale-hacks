import React, { useState, useEffect, useRef, useCallback, memo } from 'react'
import ReactMarkdown from 'react-markdown'
import logoFilter from '../assets/logo-filter.svg'
import './ChatPanel.css'

// Hook for scroll-triggered fade-in animations
function useScrollFadeIn() {
  const elementRef = useRef(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.unobserve(element)
        }
      },
      { threshold: 0.1, rootMargin: '50px' }
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return [elementRef, isVisible]
}

// Animated counter component for stats
function AnimatedCounter({ value, duration = 500 }) {
  const [displayValue, setDisplayValue] = useState(0)
  const startTimeRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    const targetValue = parseInt(value, 10) || 0
    startTimeRef.current = performance.now()

    const animate = (currentTime) => {
      const elapsed = currentTime - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)

      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(Math.round(eased * targetValue))

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [value, duration])

  return <span className="animated-counter">{displayValue}</span>
}

// TypeWriter component for character-by-character animation
function TypeWriter({ content, speed = 20, onComplete, skipAnimation = false }) {
  const [displayedContent, setDisplayedContent] = useState(skipAnimation ? content : '')
  const [isTyping, setIsTyping] = useState(!skipAnimation)
  const indexRef = useRef(0)
  const onCompleteRef = useRef(onComplete)

  // Keep ref up to date without triggering the animation effect
  useEffect(() => {
    onCompleteRef.current = onComplete
  })

  useEffect(() => {
    if (skipAnimation) {
      setDisplayedContent(content)
      setIsTyping(false)
      return
    }

    if (!content) return

    indexRef.current = 0
    setDisplayedContent('')
    setIsTyping(true)

    const timer = setInterval(() => {
      if (indexRef.current < content.length) {
        setDisplayedContent(content.slice(0, indexRef.current + 1))
        indexRef.current++
      } else {
        clearInterval(timer)
        setIsTyping(false)
        onCompleteRef.current?.()
      }
    }, speed)

    return () => clearInterval(timer)
  }, [content, speed, skipAnimation])

  return (
    <span className="typewriter-text">
      <ReactMarkdown className="markdown-content">{displayedContent}</ReactMarkdown>
      {isTyping && <span className="typewriter-cursor">|</span>}
    </span>
  )
}

// Individual message component with scroll-triggered animation
function ChatMessage({ message, index, renderContent, onOpenPdf }) {
  const [ref, isVisible] = useScrollFadeIn()

  // Determine icon based on citation type - use subtle symbols instead of emojis
  const getIcon = (citation) => {
    const display = citation.display?.toLowerCase() || ''
    if (display.includes('lab')) return '◆'
    if (display.includes('med') || display.includes('rx')) return '●'
    if (display.includes('visit') || display.includes('note')) return '■'
    if (display.includes('procedure')) return '▲'
    if (display.includes('imaging') || display.includes('radiology')) return '◇'
    return '○'
  }

  return (
    <div
      ref={ref}
      className={`chat-message chat-message-${message.role} ${
        message.isError ? 'chat-message-error' : ''
      } ${isVisible ? 'message-visible' : 'message-hidden'}`}
      style={{ '--message-index': index }}
    >
      <div className="message-header">
        <span className="message-role">
          {message.role === 'user' ? 'You' : message.model || 'Assistant'}
        </span>
        {message.gatekeeperTurns && (
          <span className="message-turns">
            <AnimatedCounter value={message.gatekeeperTurns} /> retrieval{message.gatekeeperTurns > 1 ? 's' : ''}
          </span>
        )}
        <span className="message-time">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>
      <div className="message-content">
        {message.role === 'assistant' && !message.isComplete ? (
          <div className="streaming-status">
            <span className="streaming-indicator"></span>
            <span className="streaming-text">{message.streamingStatus}</span>
          </div>
        ) : (
          renderContent(message)
        )}
      </div>
      {/* Inline citations are shown in the response text; no separate sources section */}
    </div>
  )
}

// Helper to replace [number] patterns in React children with clickable citation buttons
function processCitations(children, citationMap, onOpenPdf) {
  if (!children) return children
  return React.Children.map(children, (child) => {
    if (typeof child !== 'string') return child
    const parts = child.split(/(\[\d+\])/g)
    if (parts.length === 1) return child
    return parts.map((part, i) => {
      const match = part.match(/\[(\d+)\]/)
      if (match) {
        const idx = parseInt(match[1], 10)
        const citation = citationMap[idx]
        if (citation) {
          return (
            <button
              key={i}
              className="citation-link"
              title={citation.display}
              onClick={() => onOpenPdf?.(citation.pdf, citation.page, citation)}
            >
              [{idx}]
            </button>
          )
        }
      }
      return part
    })
  })
}

function ChatPanel({ selectedModel, onSseEvent, onQueryStart, onOpenPdf, connectionStatus, onLoveMode }) {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)
  const sessionIdRef = useRef(crypto.randomUUID())

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Parse SSE events from a text chunk
  const parseSSE = (text) => {
    const events = []
    const lines = text.split('\n')
    let currentEvent = { type: null, data: null }

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent.type = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        try {
          currentEvent.data = JSON.parse(line.slice(6))
        } catch (e) {
          currentEvent.data = line.slice(6)
        }
      } else if (line === '' && currentEvent.type && currentEvent.data) {
        events.push({ ...currentEvent })
        currentEvent = { type: null, data: null }
      }
    }

    return events
  }

  // Update the streaming status in the assistant message
  const updateStreamingStatus = (assistantMessageId, status) => {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === assistantMessageId
          ? { ...msg, streamingStatus: status }
          : msg
      )
    )
  }

  // Process an SSE event
  const processEvent = (event, assistantMessageId) => {
    const { type, data } = event

    // Emit to parent for graph panel - include type for filtering
    onSseEvent?.({ type, ...data })

    switch (type) {
      case 'deidentified_query':
        updateStreamingStatus(assistantMessageId, 'Query de-identified')
        break

      case 'cloud_thinking':
        updateStreamingStatus(assistantMessageId, data.content || 'Analyzing...')
        break

      case 'gatekeeper_query':
        updateStreamingStatus(
          assistantMessageId,
          `Searching clinical records (turn ${data.turn})`
        )
        break

      case 'gatekeeper_response':
        updateStreamingStatus(
          assistantMessageId,
          `Retrieved context from ${data.refs_added?.length || 0} sources`
        )
        break

      case 'graph_traversal':
        updateStreamingStatus(
          assistantMessageId,
          `Traversing ${data.nodes?.length || 0} nodes`
        )
        break

      case 'final_response':
        // Update the assistant message with final content and citations
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: data.content,
                  citations: data.citations || [],
                  model: data.model_used,
                  gatekeeperTurns: data.gatekeeper_turns,
                  isComplete: true,
                  streamingStatus: null,
                }
              : msg
          )
        )
        setIsLoading(false)

        // Love mode trigger - Yhack theme easter egg
        // Detect if the response diagnoses "love"
        const lowerContent = (data.content || '').toLowerCase()
        if (
          lowerContent.includes('diagnosed with love') ||
          lowerContent.includes('diagnosis: love') ||
          lowerContent.includes('diagnosis of love') ||
          lowerContent.includes('in love') ||
          lowerContent.includes('lovesick') ||
          lowerContent.includes('love syndrome') ||
          lowerContent.includes('amorosis') ||
          lowerContent.includes('new relationship') ||
          lowerContent.includes('romantic attachment') ||
          lowerContent.includes('sick with love')
        ) {
          onLoveMode?.()
        }
        break

      case 'error':
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: `Error: ${data.content}`,
                  isError: true,
                  isComplete: true,
                  streamingStatus: null,
                }
              : msg
          )
        )
        setIsLoading(false)
        break

      default:
        console.log('Unknown SSE event:', type, data)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!inputValue.trim() || isLoading) return

    const query = inputValue.trim()

    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    }

    // Create placeholder assistant message
    const assistantMessageId = Date.now() + 1
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      model: selectedModel,
      citations: [],
      isComplete: false,
      streamingStatus: 'Connecting...',
    }

    setMessages((prev) => [...prev, userMessage, assistantMessage])
    setInputValue('')
    setIsLoading(true)
    onQueryStart?.()

    // Abort any existing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: query,
          model: selectedModel,
          session_id: sessionIdRef.current,
        }),
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse and process complete SSE events from buffer
        const events = parseSSE(buffer)
        for (const event of events) {
          processEvent(event, assistantMessageId)
        }

        // Keep any incomplete event data in buffer
        const lastDoubleNewline = buffer.lastIndexOf('\n\n')
        if (lastDoubleNewline !== -1) {
          buffer = buffer.slice(lastDoubleNewline + 2)
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Request aborted')
        return
      }

      console.error('SSE error:', error)
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                content: `Connection error: ${error.message}`,
                isError: true,
                isComplete: true,
                streamingStatus: null,
              }
            : msg
        )
      )
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  // Track which messages have finished typing animation
  const [typedMessages, setTypedMessages] = useState(new Set())

  const handleTypingComplete = useCallback((messageId) => {
    setTypedMessages(prev => new Set([...prev, messageId]))
  }, [])

  // Render message content with citation links
  const renderContent = (message) => {
    if (!message.content) return null

    const shouldAnimate = message.role === 'assistant' &&
                          message.isComplete &&
                          !typedMessages.has(message.id) &&
                          !message.skipAnimation

    // If no citations, use TypeWriter for animation
    if (!message.citations || message.citations.length === 0) {
      if (shouldAnimate) {
        return (
          <div className="message-text">
            <TypeWriter
              content={message.content}
              speed={20}
              onComplete={() => handleTypingComplete(message.id)}
            />
          </div>
        )
      }
      return <div className="message-text"><ReactMarkdown className="markdown-content">{message.content}</ReactMarkdown></div>
    }

    // For messages with citations, render full markdown then make citation numbers clickable
    // We replace [number] with a placeholder, render markdown, then swap placeholders for buttons
    const citationMap = {}
    message.citations.forEach((c) => { citationMap[c.index] = c })

    return (
      <div className="message-text">
        <ReactMarkdown
          className="markdown-content"
          components={{
            // Override text rendering to inject citation buttons
            p: ({ children, ...props }) => <p {...props}>{processCitations(children, citationMap, onOpenPdf)}</p>,
            li: ({ children, ...props }) => <li {...props}>{processCitations(children, citationMap, onOpenPdf)}</li>,
            strong: ({ children, ...props }) => <strong {...props}>{processCitations(children, citationMap, onOpenPdf)}</strong>,
            em: ({ children, ...props }) => <em {...props}>{processCitations(children, citationMap, onOpenPdf)}</em>,
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    )
  }

  return (
    <div className="chat-panel">
      {/* Chat Header - simplified since model selector moved to app header */}
      <div className="chat-header">
        <span className="chat-header-title">Clinical Chat</span>
        <span className={`chat-status ${isLoading ? 'status-loading' : ''}`}>
          {isLoading ? 'Processing query...' : 'Ready'}
        </span>
      </div>

      {/* Messages Area */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon"><img src={logoFilter} alt="" style={{ width: '48px', height: '48px' }} /></div>
            <div className="chat-empty-title">Clinical Assistant</div>
            <div className="chat-empty-subtitle">
              Query patient records securely. PHI is automatically de-identified before reaching the cloud.
            </div>
            <div className="chat-empty-examples">
              <span className="example-label">Try asking</span>
              <div className="example-grid">
                <button
                  className="example-btn"
                  onClick={() => setInputValue("Tell me about John Smith's recent lab results")}
                >
                  <span className="example-icon">◆</span>
                  <span className="example-text">John Smith's recent lab results</span>
                  <span className="example-arrow">→</span>
                </button>
                <button
                  className="example-btn"
                  onClick={() => setInputValue("What medications is Sarah Johnson currently taking?")}
                >
                  <span className="example-icon">●</span>
                  <span className="example-text">Sarah Johnson's current medications</span>
                  <span className="example-arrow">→</span>
                </button>
                <button
                  className="example-btn"
                  onClick={() => setInputValue("Summarize Michael Chen's visit history")}
                >
                  <span className="example-icon">■</span>
                  <span className="example-text">Michael Chen's visit history</span>
                  <span className="example-arrow">→</span>
                </button>
                <button
                  className="example-btn"
                  onClick={() => setInputValue("Valentine has racing heart and daydreaming - diagnosis?")}
                >
                  <span className="example-icon">♥</span>
                  <span className="example-text">Valentine's symptoms</span>
                  <span className="example-arrow">→</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            {messages.map((message, index) => (
              <ChatMessage
                key={message.id}
                message={message}
                index={index}
                renderContent={renderContent}
                onOpenPdf={onOpenPdf}
              />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Area */}
      <form className="chat-input-area" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder="Ask about a patient..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={!inputValue.trim() || isLoading}
          aria-label="Send message"
        >
          <span className="send-icon">↑</span>
        </button>
      </form>
    </div>
  )
}

export default memo(ChatPanel)
