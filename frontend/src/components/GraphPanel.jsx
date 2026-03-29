import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph3D from '3d-force-graph'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass'
import './GraphPanel.css'

function GraphPanel({ traversalData, sseEvents }) {
  const containerRef = useRef(null)
  const graphRef = useRef(null)
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [hoveredNode, setHoveredNode] = useState(null)
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })

  // Refs to track current hover/selection for the render callback
  const hoveredNodeRef = useRef(null)
  const selectedNodeRef = useRef(null)

  // Fetch graph data on mount
  useEffect(() => {
    async function fetchGraph() {
      try {
        const response = await fetch('/api/graph')
        const data = await response.json()

        // Transform edges to links format expected by 3d-force-graph
        const links = data.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          type: edge.type,
        }))

        setGraphData({ nodes: data.nodes, links })
        setStats({ nodes: data.nodes.length, edges: links.length })
      } catch (error) {
        console.error('Failed to fetch graph:', error)
      }
    }
    fetchGraph()
  }, [])

  // Initialize 3D graph
  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return

    // Clean up existing graph
    if (graphRef.current) {
      graphRef.current._destructor?.()
    }

    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    // Monochromatic color palette - soft muted blues/grays
    const monoColor = '#6A7B92'  // Soft slate blue
    const monoColorHover = '#8EA0B5'  // Subtle lift on hover

    // Create the 3D force graph with modern, clean aesthetic
    const graph = ForceGraph3D()(container)
      .width(width)
      .height(height)
      .backgroundColor('#030305')
      .showNavInfo(false)
      // Custom node rendering with translucent spheres
      .nodeThreeObject((node) => {
        const isHovered = hoveredNodeRef.current?.id === node.id
        const isSelected = selectedNodeRef.current?.id === node.id
        const isHighlighted = isHovered || isSelected

        // Create sphere geometry
        const geometry = new THREE.SphereGeometry(node.size * 0.7, 24, 24)

        // Use monochromatic color with clear hover distinction
        const color = new THREE.Color(isHighlighted ? monoColorHover : monoColor)
        const material = new THREE.MeshPhongMaterial({
          color: color,
          transparent: true,
          opacity: isHighlighted ? 0.75 : 0.55,
          shininess: isHighlighted ? 80 : 40,
          emissive: color,
          emissiveIntensity: isHighlighted ? 0.35 : 0.1,
        })

        const sphere = new THREE.Mesh(geometry, material)

        // Add soft outer glow on hover
        if (isHighlighted) {
          const glowGeometry = new THREE.SphereGeometry(node.size * 1.05, 16, 16)
          const glowMaterial = new THREE.MeshBasicMaterial({
            color: new THREE.Color(monoColorHover),
            transparent: true,
            opacity: 0.1,
          })
          const glow = new THREE.Mesh(glowGeometry, glowMaterial)
          sphere.add(glow)
        }

        return sphere
      })
      .nodeLabel((node) => node.label)
      // Thin, delicate links - monochromatic but visible
      .linkColor(() => 'rgba(106, 123, 146, 0.5)')
      .linkWidth(0.5)
      .linkOpacity(0.6)
      // Hover effects
      .onNodeHover((node) => {
        setHoveredNode(node || null)
        container.style.cursor = node ? 'pointer' : 'default'
      })
      .onNodeClick((node) => {
        setSelectedNode(node)
        // Focus camera on clicked node with smooth transition
        const distance = 100
        const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z)
        graph.cameraPosition(
          {
            x: node.x * distRatio,
            y: node.y * distRatio,
            z: node.z * distRatio,
          },
          node,
          1200
        )
      })
      .onBackgroundClick(() => {
        setSelectedNode(null)
      })

    // Add subtle bloom effect - very soft
    const bloomPass = new UnrealBloomPass()
    bloomPass.strength = 0.4
    bloomPass.radius = 0.6
    bloomPass.threshold = 0.3
    graph.postProcessingComposer().addPass(bloomPass)

    // Add ambient and directional lighting for depth
    const scene = graph.scene()
    scene.add(new THREE.AmbientLight(0xffffff, 0.6))
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4)
    directionalLight.position.set(100, 100, 100)
    scene.add(directionalLight)

    // Set graph data
    graph.graphData(graphData)

    // Store reference
    graphRef.current = graph

    // Handle resize
    const handleResize = () => {
      if (containerRef.current && graphRef.current) {
        graphRef.current
          .width(containerRef.current.clientWidth)
          .height(containerRef.current.clientHeight)
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [graphData])

  // Update refs and refresh nodes on hover/selection change
  useEffect(() => {
    hoveredNodeRef.current = hoveredNode
    selectedNodeRef.current = selectedNode

    if (graphRef.current) {
      // Force re-render of all nodes
      graphRef.current.refresh()
    }
  }, [hoveredNode, selectedNode])

  // Close info card
  const closeInfoCard = useCallback(() => {
    setSelectedNode(null)
  }, [])

  // Render metadata fields
  const renderMetadata = (metadata) => {
    if (!metadata) return null

    const entries = Object.entries(metadata).filter(
      ([key]) => !['name', 'mrn'].includes(key) // Don't show PHI fields in card
    )

    return entries.map(([key, value]) => (
      <div key={key} className="info-field">
        <span className="info-label">{formatLabel(key)}</span>
        <span className="info-value">{String(value)}</span>
      </div>
    ))
  }

  // Format field labels
  const formatLabel = (key) => {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
  }

  // Get node type display name
  const getTypeDisplay = (type) => {
    const types = {
      patient: 'Patient',
      visit: 'Visit',
      condition: 'Condition',
      medication: 'Medication',
      lab_result: 'Lab Result',
      procedure: 'Procedure',
      provider: 'Provider',
    }
    return types[type] || type
  }

  return (
    <div className="graph-panel">
      {/* Graph Header */}
      <div className="graph-header">
        <span className="graph-title">Knowledge Graph</span>
        <span className="graph-stats">
          {stats.nodes} nodes · {stats.edges} edges
        </span>
      </div>

      {/* 3D Graph Canvas */}
      <div className="graph-canvas" ref={containerRef}>
        {graphData.nodes.length === 0 && (
          <div className="graph-loading">Loading graph...</div>
        )}
      </div>

      {/* Legend Overlay - Minimal */}
      <div className="graph-legend-overlay">
        <div className="legend-item">
          <span className="legend-dot" style={{ background: '#6B7C95' }}></span>
          <span>Clinical Entities</span>
        </div>
        <div className="legend-item legend-hint">
          Click node for details
        </div>
      </div>

      {/* Node Info Card */}
      {selectedNode && (
        <div className="info-card">
          <div className="info-card-header">
            <span className="info-card-type">
              {getTypeDisplay(selectedNode.type)}
            </span>
            <button className="info-card-close" onClick={closeInfoCard}>
              ×
            </button>
          </div>
          <div className="info-card-title">{selectedNode.label}</div>
          <div className="info-card-metadata">
            {renderMetadata(selectedNode.metadata)}
          </div>
          {selectedNode.source_pdf && (
            <button
              className="info-card-pdf-btn"
              onClick={() => {
                // Phase 5 will handle PDF viewer
                console.log('Open PDF:', selectedNode.source_pdf, selectedNode.source_page)
              }}
            >
              View Source PDF (p.{selectedNode.source_page})
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default GraphPanel
