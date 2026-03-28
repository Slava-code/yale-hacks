import { useState, useEffect, useRef } from 'react'
import './ChatPanel.css'

function ChatPanel({ selectedModel, onModelChange }) {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [models, setModels] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)

  // Fetch available models on mount
  useEffect(() => {
    async function fetchModels() {
      try {
        const response = await fetch('/api/models')
        const data = await response.json()
        setModels(data.models || [])
      } catch (error) {
        console.error('Failed to fetch models:', error)
        // Fallback to hardcoded models
        setModels([
          { id: 'claude', name: 'Claude', available: true },
          { id: 'gpt4', name: 'GPT-4', available: true },
          { id: 'gemini', name: 'Gemini', available: true },
        ])
      }
    }
    fetchModels()
  }, [])

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!inputValue.trim() || isLoading) return

    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)

    // For Phase 1, just add a placeholder response
    // Phase 2 will implement actual SSE streaming
    setTimeout(() => {
      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `[Phase 2 will connect to ${selectedModel} via SSE streaming]`,
        timestamp: new Date().toISOString(),
        model: selectedModel,
      }
      setMessages((prev) => [...prev, assistantMessage])
      setIsLoading(false)
    }, 500)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
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
        <span className="model-status">
          {isLoading ? 'Thinking...' : 'Ready'}
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
                className={`chat-message chat-message-${message.role}`}
              >
                <div className="message-header">
                  <span className="message-role">
                    {message.role === 'user' ? 'You' : message.model || 'Assistant'}
                  </span>
                  <span className="message-time">
                    {new Date(message.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
                <div className="message-content">{message.content}</div>
              </div>
            ))}
            {isLoading && (
              <div className="chat-message chat-message-assistant">
                <div className="message-header">
                  <span className="message-role">{selectedModel}</span>
                </div>
                <div className="message-content message-loading">
                  <span className="loading-dot"></span>
                  <span className="loading-dot"></span>
                  <span className="loading-dot"></span>
                </div>
              </div>
            )}
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
