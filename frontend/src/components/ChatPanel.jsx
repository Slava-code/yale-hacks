import { useState, useEffect, useRef } from 'react'
import './ChatPanel.css'

function ChatPanel({ selectedModel, onModelChange, onSseEvent, onQueryStart, onOpenPdf }) {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [models, setModels] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)

  // Fetch available models on mount
  useEffect(() => {
    async function fetchModels() {
      try {
        const response = await fetch('/api/models')
        const data = await response.json()
        setModels(data.models || [])
      } catch (error) {
        console.error('Failed to fetch models:', error)
        setModels([
          { id: 'claude', name: 'Claude', available: true },
          { id: 'gpt4', name: 'GPT-4', available: true },
          { id: 'gemini', name: 'Gemini', available: true },
        ])
      }
    }
    fetchModels()
  }, [])

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

  // Render message content with citation links
  const renderContent = (message) => {
    if (!message.content) return null

    // If no citations, just return the content
    if (!message.citations || message.citations.length === 0) {
      return <div className="message-text">{message.content}</div>
    }

    // Replace [N] with clickable citation links
    const parts = message.content.split(/(\[\d+\])/g)

    return (
      <div className="message-text">
        {parts.map((part, index) => {
          const match = part.match(/\[(\d+)\]/)
          if (match) {
            const citationIndex = parseInt(match[1], 10)
            const citation = message.citations.find((c) => c.index === citationIndex)
            if (citation) {
              return (
                <button
                  key={index}
                  className="citation-link"
                  title={citation.display}
                  onClick={() => {
                    onOpenPdf?.(citation.pdf, citation.page, citation)
                  }}
                >
                  [{citationIndex}]
                </button>
              )
            }
          }
          return <span key={index}>{part}</span>
        })}
      </div>
    )
  }

  return (
    <div className="chat-panel">
      {/* Model Selector */}
      <div className="chat-header">
        <select
          className="model-selector"
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={isLoading}
        >
          {models.map((model) => (
            <option key={model.id} value={model.id} disabled={!model.available}>
              {model.name}
            </option>
          ))}
        </select>
        <span className={`model-status ${isLoading ? 'status-loading' : ''}`}>
          {isLoading ? 'Processing...' : 'Ready'}
        </span>
      </div>

      {/* Messages Area */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">⚕</div>
            <div className="chat-empty-title">MedGate Clinical Assistant</div>
            <div className="chat-empty-subtitle">
              Ask about a patient using their name. PHI will be automatically
              de-identified before reaching the cloud model.
            </div>
            <div className="chat-empty-examples">
              <span className="example-label">Try:</span>
              <button
                className="example-btn"
                onClick={() => setInputValue("Tell me about John Smith's recent lab results")}
              >
                "Tell me about John Smith's recent lab results"
              </button>
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <div
                key={message.id}
                className={`chat-message chat-message-${message.role} ${
                  message.isError ? 'chat-message-error' : ''
                }`}
              >
                <div className="message-header">
                  <span className="message-role">
                    {message.role === 'user' ? 'You' : message.model || 'Assistant'}
                  </span>
                  {message.gatekeeperTurns && (
                    <span className="message-turns">
                      {message.gatekeeperTurns} retrieval{message.gatekeeperTurns > 1 ? 's' : ''}
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
                      <span className="streaming-text">{message.streamingStatus}</span>
                      <span className="streaming-pulse"></span>
                    </div>
                  ) : (
                    renderContent(message)
                  )}
                </div>
                {message.citations && message.citations.length > 0 && (
                  <div className="message-citations">
                    <span className="citations-label">Sources:</span>
                    {message.citations.map((citation) => (
                      <button
                        key={citation.ref_id}
                        className="citation-chip"
                        title={`${citation.pdf}, page ${citation.page}`}
                        onClick={() => onOpenPdf?.(citation.pdf, citation.page, citation)}
                      >
                        [{citation.index}] {citation.display}
                      </button>
                    ))}
                  </div>
                )}
              </div>
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
        >
          Send
        </button>
      </form>
    </div>
  )
}

export default ChatPanel
