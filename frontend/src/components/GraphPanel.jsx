import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph3D from '3d-force-graph'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass'
import * as d3 from 'd3-force-3d'
import './GraphPanel.css'

// Shared geometries - created once, reused for all nodes
const SHARED_GEOMETRY = new THREE.SphereGeometry(1, 12, 12)  // Unit sphere, scaled per node
const SHARED_GLOW_GEOMETRY = new THREE.SphereGeometry(1, 8, 8)

// Shared materials - one per visual state, reused across nodes
const MATERIALS = {
  default: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#4A6B8A'),
    transparent: true,
    opacity: 0.55,
  }),
  hovered: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#5A8AB5'),
    transparent: true,
    opacity: 0.75,
  }),
  traversed: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#17D4BF'),
    transparent: true,
    opacity: 0.64,
  }),
  traversedHovered: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#34F4DC'),
    transparent: true,
    opacity: 0.72,
  }),
  pulsing: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#34F4DC'),
    transparent: true,
    opacity: 0.82,
  }),
  fading: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#17D4BF'),
    transparent: true,
    opacity: 0.72,
  }),
  glow: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#17D4BF'),
    transparent: true,
    opacity: 0.15,
  }),
  glowHover: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#5A8AB5'),
    transparent: true,
    opacity: 0.1,
  }),
}

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

  // Node mesh cache - reuse meshes instead of recreating
  const nodeMeshCache = useRef(new Map())

  // Debounced refresh
  const refreshTimeoutRef = useRef(null)
  const scheduleRefresh = useCallback(() => {
    if (refreshTimeoutRef.current) return  // Already scheduled
    refreshTimeoutRef.current = setTimeout(() => {
      refreshTimeoutRef.current = null
      if (graphRef.current) {
        graphRef.current.refresh()
      }
    }, 16)  // ~60fps max
  }, [])

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
    const traversedColor = '#17D4BF'  // Accent teal green (15% brighter)
    const pulseColor = '#34F4DC'  // Lighter teal for pulse (15% brighter)

    // Create the 3D force graph with modern, clean aesthetic
    const graph = ForceGraph3D()(container)
      .width(width)
      .height(height)
      .backgroundColor('#030305')
      .showNavInfo(false)
      .enableNodeDrag(false)  // Disable node dragging - clicking shows info card only
      // Custom node rendering - uses cached meshes and shared geometry/materials
      .nodeThreeObject((node) => {
        const isHovered = hoveredNodeRef.current?.id === node.id
        const isSelected = selectedNodeRef.current?.id === node.id
        const isTraversed = traversedNodesRef.current.has(node.id)
        const isPulsing = pulsingNodesRef.current.has(node.id)
        const isFading = fadingNodesRef.current.has(node.id)
        const isHighlighted = isHovered || isSelected
        const needsGlow = isHighlighted || isPulsing || isFading

        // Determine material based on state
        let material
        if (isPulsing) {
          material = MATERIALS.pulsing
        } else if (isFading) {
          material = MATERIALS.fading
        } else if (isTraversed && isHighlighted) {
          material = MATERIALS.traversedHovered
        } else if (isTraversed) {
          material = MATERIALS.traversed
        } else if (isHighlighted) {
          material = MATERIALS.hovered
        } else {
          material = MATERIALS.default
        }

        // Check cache for existing mesh
        const cached = nodeMeshCache.current.get(node.id)
        if (cached) {
          // Update material if changed
          cached.sphere.material = material
          // Handle glow visibility
          if (cached.glow) {
            cached.glow.visible = needsGlow
            if (needsGlow) {
              cached.glow.material = (isPulsing || isFading || isTraversed) ? MATERIALS.glow : MATERIALS.glowHover
              const glowScale = isPulsing ? 1.2 : (isFading ? 1.12 : 1.05)
              cached.glow.scale.setScalar(glowScale)
            }
          }
          return cached.sphere
        }

        // Create new mesh with shared geometry
        const sphere = new THREE.Mesh(SHARED_GEOMETRY, material)
        const scale = node.size * 0.7
        sphere.scale.setScalar(scale)

        // Create glow child (always present, toggle visibility)
        const glow = new THREE.Mesh(SHARED_GLOW_GEOMETRY, MATERIALS.glow)
        glow.visible = needsGlow
        glow.scale.setScalar(needsGlow ? (isPulsing ? 1.2 : 1.05) : 1.05)
        sphere.add(glow)

        // Cache the mesh
        nodeMeshCache.current.set(node.id, { sphere, glow })

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
          return 'rgba(23, 212, 191, 0.5)'  // Accent teal green for traversed edges (15% brighter)
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

    // Add subtle bloom effect - reduced for performance
    const bloomPass = new UnrealBloomPass()
    bloomPass.strength = 0.2
    bloomPass.radius = 0.4
    bloomPass.threshold = 0.4
    graph.postProcessingComposer().addPass(bloomPass)

    // Add ambient and directional lighting for depth
    const scene = graph.scene()
    scene.add(new THREE.AmbientLight(0xffffff, 0.6))
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4)
    directionalLight.position.set(100, 100, 100)
    scene.add(directionalLight)

    // Configure forces for hierarchical galaxy-sphere layout
    // High-connectivity nodes (suns) at center of mini-clusters
    // Mini-clusters connected via shared nodes, all within a sphere
    const nodeCount = graphData.nodes.length
    const baseRadius = Math.max(300, Math.cbrt(nodeCount) * 60)

    // Calculate node degrees (connectivity) for hierarchical positioning
    const nodeDegree = {}
    graphData.nodes.forEach(n => nodeDegree[n.id] = 0)
    graphData.links.forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source
      const targetId = typeof link.target === 'object' ? link.target.id : link.target
      nodeDegree[sourceId] = (nodeDegree[sourceId] || 0) + 1
      nodeDegree[targetId] = (nodeDegree[targetId] || 0) + 1
    })
    const maxDegree = Math.max(...Object.values(nodeDegree), 1)

    // Radial force - high-degree nodes (suns) closer to center, satellites at edges
    // 15% more dense toward center
    graph.d3Force('radial', d3.forceRadial(
      node => {
        const degree = nodeDegree[node.id] || 0
        const normalizedDegree = degree / maxDegree
        // High degree = closer to center, low degree = toward edge
        // Reduced by 15% to pull everything closer to center
        return baseRadius * 0.85 * (0.25 + 0.6 * (1 - normalizedDegree))
      },
      0, 0, 0
    ).strength(0.45))

    // Center force - keeps the galaxy centered
    graph.d3Force('center', d3.forceCenter(0, 0, 0))

    // Charge force - moderate repulsion, evenly spaces clusters
    graph.d3Force('charge', d3.forceManyBody()
      .strength(node => {
        const degree = nodeDegree[node.id] || 0
        // High-degree nodes repel more (they're suns, need space for satellites)
        return -60 - (degree * 3)
      })
      .distanceMin(15)
      .distanceMax(baseRadius * 2)
    )

    // Link force - creates spherical mini-clusters around suns
    graph.d3Force('link')
      .distance(link => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const sourceDegree = nodeDegree[sourceId] || 1
        const targetDegree = nodeDegree[targetId] || 1
        const maxLinkDegree = Math.max(sourceDegree, targetDegree)
        // Consistent orbital distance based on sun's size - creates spherical shells
        return 25 + (maxLinkDegree * 2)
      })
      .strength(link => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const sourceDegree = nodeDegree[sourceId] || 1
        const targetDegree = nodeDegree[targetId] || 1
        // Strong pull to keep satellites in tight spherical orbit
        return 0.9
      })

    // Collision force - spherical spacing within clusters (reduced iterations)
    graph.d3Force('collision', d3.forceCollide()
      .radius(node => {
        const degree = nodeDegree[node.id] || 0
        // Suns get more space, satellites pack evenly around them
        return node.size * (1.8 + degree * 0.15)
      })
      .strength(0.8)
      .iterations(1)
    )

    // Add cluster cohesion - satellites attract each other slightly (forms spherical shell)
    graph.d3Force('cluster', d3.forceManyBody()
      .strength(node => {
        const degree = nodeDegree[node.id] || 0
        // Low-degree nodes (satellites) attract each other gently
        // High-degree nodes (suns) don't attract - they repel via charge
        return degree < 3 ? 5 : 0
      })
      .distanceMin(10)
      .distanceMax(60)
    )

    // Simulation tuning - faster convergence for performance
    graph.d3AlphaDecay(0.04)  // Faster decay
    graph.d3VelocityDecay(0.4)  // More damping = less jitter
    graph.warmupTicks(150)  // More pre-compute = less runtime sim
    graph.cooldownTicks(100)  // Settle faster

    // Set graph data
    graph.graphData(graphData)

    // Store reference
    graphRef.current = graph

    // Set initial camera position to view the full galaxy-sphere
    const cameraDistance = baseRadius * 3
    setTimeout(() => {
      graph.cameraPosition(
        { x: cameraDistance * 0.7, y: cameraDistance * 0.5, z: cameraDistance * 0.7 },
        { x: 0, y: 0, z: 0 },
        0
      )
    }, 100)

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
      nodeMeshCache.current.clear()
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
    }
  }, [graphData])

  // Update refs and refresh nodes on hover/selection change
  useEffect(() => {
    hoveredNodeRef.current = hoveredNode
    selectedNodeRef.current = selectedNode
    scheduleRefresh()
  }, [hoveredNode, selectedNode, scheduleRefresh])

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

        scheduleRefresh()
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

        scheduleRefresh()
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

        scheduleRefresh()
      }, index * delayPerNode + 3100)  // Fade lasts 2300ms (800 + 1500 extra)

      timers.push(settleTimer)
    })

    return () => timers.forEach(t => clearTimeout(t))
  }, [traversalData, scheduleRefresh])

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
          <span className="legend-dot" style={{ background: '#17D4BF' }}></span>
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
