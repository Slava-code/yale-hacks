import './ChatPanel.css'

function ChatPanel({ selectedModel, onModelChange }) {
  return (
    <div className="chat-panel">
      {/* Model Selector */}
      <div className="chat-header">
        <select
          className="model-selector"
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
        >
          <option value="claude">Claude</option>
          <option value="gpt4">GPT-4</option>
          <option value="gemini">Gemini</option>
        </select>
      </div>

      {/* Messages Area - Placeholder */}
      <div className="chat-messages">
        <div className="panel-placeholder">
          <div className="panel-placeholder-icon">💬</div>
          <div className="panel-placeholder-title">Chat Interface</div>
          <div className="panel-placeholder-subtitle">
            Phase 1: Chat UI will be implemented here
          </div>
        </div>
      </div>

      {/* Input Area - Placeholder */}
      <div className="chat-input-area">
        <input
          type="text"
          className="chat-input"
          placeholder="Ask about a patient..."
          disabled
        />
        <button className="chat-send-btn" disabled>
          Send
        </button>
      </div>
    </div>
  )
}

export default ChatPanel
