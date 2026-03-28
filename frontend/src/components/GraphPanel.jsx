import './GraphPanel.css'

function GraphPanel({ traversalData, sseEvents }) {
  // traversalData and sseEvents will be used in Phase 3/4
  return (
    <div className="graph-panel">
      {/* Graph Header */}
      <div className="graph-header">
        <span className="graph-title">Knowledge Graph</span>
        <span className="graph-stats">Phase 3: 3D visualization</span>
      </div>

      {/* Graph Canvas - Placeholder */}
      <div className="graph-canvas">
        <div className="panel-placeholder">
          <div className="panel-placeholder-icon">🔮</div>
          <div className="panel-placeholder-title">3D Knowledge Graph</div>
          <div className="panel-placeholder-subtitle">
            Phase 3: 3d-force-graph will render here
          </div>
          <div className="graph-legend">
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-patient)' }}></span>
              <span>Patient</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-condition)' }}></span>
              <span>Condition</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-medication)' }}></span>
              <span>Medication</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-lab)' }}></span>
              <span>Lab Result</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-visit)' }}></span>
              <span>Visit</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: 'var(--node-provider)' }}></span>
              <span>Provider</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default GraphPanel
