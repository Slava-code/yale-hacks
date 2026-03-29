import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph3D from '3d-force-graph'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass'
import './GraphPanel.css'

function GraphPanel({ traversalData, sseEvents, onOpenPdf }) {
  const containerRef = useRef(null)
  const graphRef = useRef(null)
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [hoveredNode, setHoveredNode] = useState(null)
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })

  // Traversal state - tracks nodes/edges accessed during queries
  const [traversedNodes, setTraversedNodes] = useState(new Set())
  const [traversedEdges, setTraversedEdges] = useState(new Set())
  const [pulsingNodes, setPulsingNodes] = useState(new Set())
  const [fadingNodes, setFadingNodes] = useState(new Set())  // Buffer before fully fading

  // Refs to track current state for the render callback
  const hoveredNodeRef = useRef(null)
  const selectedNodeRef = useRef(null)
  const traversedNodesRef = useRef(new Set())
  const traversedEdgesRef = useRef(new Set())
  const pulsingNodesRef = useRef(new Set())
  const fadingNodesRef = useRef(new Set())

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

    // Color palette - Clinical Noir theme with Stripe-inspired refinement
    const monoColor = '#4A6B8A'  // Muted clinical blue (based on --node-patient)
    const monoColorHover = '#5A8AB5'  // Subtle lift on hover
    const traversedColor = '#4A90D9'  // Node patient blue from design system
    const pulseColor = '#6BA3E0'  // Lighter pulse blue

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
        const isTraversed = traversedNodesRef.current.has(node.id)
        const isPulsing = pulsingNodesRef.current.has(node.id)
        const isFading = fadingNodesRef.current.has(node.id)
        const isHighlighted = isHovered || isSelected

        // Create sphere geometry
        const geometry = new THREE.SphereGeometry(node.size * 0.7, 24, 24)

        // Determine color based on state (traversal uses subtle blue tones)
        let nodeColor, nodeOpacity, emissiveIntensity
        if (isPulsing) {
          nodeColor = pulseColor
          nodeOpacity = 0.68
          emissiveIntensity = 0.45
        } else if (isFading) {
          // Buffer state - intermediate between pulse and settled
          nodeColor = traversedColor
          nodeOpacity = 0.6
          emissiveIntensity = 0.3
        } else if (isTraversed) {
          nodeColor = isHighlighted ? pulseColor : traversedColor
          nodeOpacity = isHighlighted ? 0.6 : 0.53
          emissiveIntensity = isHighlighted ? 0.34 : 0.19
        } else if (isHighlighted) {
          nodeColor = monoColorHover
          nodeOpacity = 0.75
          emissiveIntensity = 0.35
        } else {
          nodeColor = monoColor
          nodeOpacity = 0.55
          emissiveIntensity = 0.1
        }

        const color = new THREE.Color(nodeColor)
        const material = new THREE.MeshPhongMaterial({
          color: color,
          transparent: true,
          opacity: nodeOpacity,
          shininess: isPulsing ? 120 : (isHighlighted || isTraversed ? 80 : 40),
          emissive: color,
          emissiveIntensity: emissiveIntensity,
        })

        const sphere = new THREE.Mesh(geometry, material)

        // Add outer glow for highlighted, pulsing, or fading nodes
        if (isHighlighted || isPulsing || isFading) {
          const glowSize = isPulsing ? 1.2 : (isFading ? 1.12 : 1.05)
          const glowOpacity = isPulsing ? 0.2 : (isFading ? 0.15 : 0.1)
          const glowGeometry = new THREE.SphereGeometry(node.size * glowSize, 16, 16)
          const glowMaterial = new THREE.MeshBasicMaterial({
            color: new THREE.Color(isPulsing || isFading ? pulseColor : monoColorHover),
            transparent: true,
            opacity: glowOpacity,
          })
          const glow = new THREE.Mesh(glowGeometry, glowMaterial)
          sphere.add(glow)
        }

        return sphere
      })
      .nodeLabel((node) => node.label)
      // Dynamic link coloring based on traversal
      .linkColor((link) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const reverseKey = `${targetId}->${sourceId}`

        if (traversedEdgesRef.current.has(edgeKey) || traversedEdgesRef.current.has(reverseKey)) {
          return 'rgba(74, 144, 217, 0.5)'  // Clinical blue for traversed edges
        }
        return 'rgba(74, 107, 138, 0.4)'  // Muted clinical blue
      })
      .linkWidth((link) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const reverseKey = `${targetId}->${sourceId}`

        if (traversedEdgesRef.current.has(edgeKey) || traversedEdgesRef.current.has(reverseKey)) {
          return 0.8  // Thicker for traversed edges
        }
        return 0.5
      })
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

    // Add subtle bloom effect - Stripe-inspired soft glow
    const bloomPass = new UnrealBloomPass()
    bloomPass.strength = 0.35
    bloomPass.radius = 0.8
    bloomPass.threshold = 0.25
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

  // Handle traversal events - highlight accessed nodes/edges sequentially
  useEffect(() => {
    if (!traversalData || !traversalData.nodes) return

    const nodeList = traversalData.nodes
    const newEdges = new Set(
      (traversalData.edges || []).map(e => `${e.source}->${e.target}`)
    )

    // Add edges immediately
    setTraversedEdges(prev => {
      const updated = new Set([...prev, ...newEdges])
      traversedEdgesRef.current = updated
      return updated
    })

    // Animate nodes one by one with smooth buffer fade (Stripe-inspired timing)
    const timers = []
    const delayPerNode = 100  // ms between each node highlight (snappy sequencing)

    nodeList.forEach((nodeId, index) => {
      // Start pulse for this node
      const startTimer = setTimeout(() => {
        setPulsingNodes(prev => {
          const updated = new Set([...prev, nodeId])
          pulsingNodesRef.current = updated
          return updated
        })

        // Add to traversed set
        setTraversedNodes(prev => {
          const updated = new Set([...prev, nodeId])
          traversedNodesRef.current = updated
          return updated
        })

        if (graphRef.current) {
          graphRef.current.refresh()
        }
      }, index * delayPerNode)

      timers.push(startTimer)

      // Transition from pulse to fading (extended buffer state)
      const fadeTimer = setTimeout(() => {
        setPulsingNodes(prev => {
          const updated = new Set([...prev])
          updated.delete(nodeId)
          pulsingNodesRef.current = updated
          return updated
        })

        setFadingNodes(prev => {
          const updated = new Set([...prev, nodeId])
          fadingNodesRef.current = updated
          return updated
        })

        if (graphRef.current) {
          graphRef.current.refresh()
        }
      }, index * delayPerNode + 800)  // Pulse lasts 800ms

      timers.push(fadeTimer)

      // End fading state (settle into traversed) - extended by 1.5s
      const settleTimer = setTimeout(() => {
        setFadingNodes(prev => {
          const updated = new Set([...prev])
          updated.delete(nodeId)
          fadingNodesRef.current = updated
          return updated
        })

        if (graphRef.current) {
          graphRef.current.refresh()
        }
      }, index * delayPerNode + 3100)  // Fade lasts 2300ms (800 + 1500 extra)

      timers.push(settleTimer)
    })

    return () => timers.forEach(t => clearTimeout(t))
  }, [traversalData])

  // Clear traversal state when a new query starts
  useEffect(() => {
    // Look for query start signal in sseEvents
    const hasNewQuery = sseEvents.some(e => e.type === 'deidentified_query')
    if (sseEvents.length === 1 && hasNewQuery) {
      setTraversedNodes(new Set())
      setTraversedEdges(new Set())
      setPulsingNodes(new Set())
      traversedNodesRef.current = new Set()
      traversedEdgesRef.current = new Set()
      pulsingNodesRef.current = new Set()
    }
  }, [sseEvents])

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
          <span className="legend-dot" style={{ background: '#4A6B8A' }}></span>
          <span>Entities</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: '#4A90D9' }}></span>
          <span>Accessed</span>
        </div>
        {traversedNodes.size > 0 && (
          <div className="legend-item legend-count">
            {traversedNodes.size} accessed
          </div>
        )}
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
                onOpenPdf?.(selectedNode.source_pdf, selectedNode.source_page)
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
