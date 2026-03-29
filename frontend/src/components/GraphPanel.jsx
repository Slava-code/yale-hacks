import { useEffect, useRef, useState, useCallback, memo } from 'react'
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
    color: new THREE.Color('#1FFFEA'),  // 20% brighter cyan
    transparent: true,
    opacity: 0.78,  // Increased from 0.64
  }),
  traversedHovered: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#5CFFFF'),  // Brighter hover state
    transparent: true,
    opacity: 0.88,  // Increased from 0.72
  }),
  pulsing: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#5CFFFF'),  // Bright white-cyan for active pulse
    transparent: true,
    opacity: 0.95,  // Near full opacity for pop
  }),
  fading: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#2BFFE8'),  // Bright cyan fading
    transparent: true,
    opacity: 0.85,  // Increased from 0.72
  }),
  glow: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#1FFFEA'),  // Brighter glow
    transparent: true,
    opacity: 0.25,  // Increased from 0.15 for more pop
  }),
  glowHover: new THREE.MeshBasicMaterial({
    color: new THREE.Color('#5A8AB5'),
    transparent: true,
    opacity: 0.1,
  }),
}

function GraphPanel({ traversalData, sseEvents, onOpenPdf, isVisible = true, queryGeneration = 0 }) {
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

    // ========== HIERARCHICAL SOLAR SYSTEM LAYOUT ==========
    // 1. Calculate node degrees (connectivity)
    const nodeDegree = {}
    graphData.nodes.forEach(n => nodeDegree[n.id] = 0)
    graphData.links.forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source
      const targetId = typeof link.target === 'object' ? link.target.id : link.target
      nodeDegree[sourceId] = (nodeDegree[sourceId] || 0) + 1
      nodeDegree[targetId] = (nodeDegree[targetId] || 0) + 1
    })
    const maxDegree = Math.max(...Object.values(nodeDegree), 1)

    // 2. Identify "suns" (high-connectivity nodes) - threshold: top 15% or deg >= 10
    const sortedByDegree = [...graphData.nodes].sort((a, b) => nodeDegree[b.id] - nodeDegree[a.id])
    const sunThreshold = Math.max(3, nodeDegree[sortedByDegree[Math.floor(sortedByDegree.length * 0.15)]?.id] || 3)
    let suns = sortedByDegree.filter(n => nodeDegree[n.id] >= sunThreshold)
    // Guarantee at least one sun — pick the highest-degree node
    if (suns.length === 0 && sortedByDegree.length > 0) {
      suns = [sortedByDegree[0]]
    }
    const centralSun = suns[0]  // Highest degree node = center of universe
    const sunSet = new Set(suns.map(s => s.id))

    // 3. Build adjacency for cluster assignment
    const adjacency = {}
    graphData.nodes.forEach(n => adjacency[n.id] = [])
    graphData.links.forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source
      const targetId = typeof link.target === 'object' ? link.target.id : link.target
      adjacency[sourceId].push(targetId)
      adjacency[targetId].push(sourceId)
    })

    // 4. Assign each satellite to its nearest sun via BFS
    const nodeToSun = {}
    const sunSatellites = {}
    suns.forEach(s => {
      nodeToSun[s.id] = s.id  // Suns belong to themselves
      sunSatellites[s.id] = []
    })

    // BFS from each sun to claim nearby unclaimed nodes
    const claimed = new Set(suns.map(s => s.id))
    const queue = suns.map(s => ({ nodeId: s.id, sunId: s.id, dist: 0 }))

    while (queue.length > 0) {
      const { nodeId, sunId, dist } = queue.shift()
      for (const neighborId of adjacency[nodeId]) {
        if (!claimed.has(neighborId)) {
          claimed.add(neighborId)
          nodeToSun[neighborId] = sunId
          sunSatellites[sunId].push(neighborId)
          queue.push({ nodeId: neighborId, sunId, dist: dist + 1 })
        }
      }
    }

    // Handle disconnected nodes - assign to nearest sun by degree similarity
    graphData.nodes.forEach(n => {
      if (!claimed.has(n.id)) {
        // Assign to a random sun (these are isolated nodes like disease_reference)
        const randomSun = suns[Math.floor(Math.random() * suns.length)]
        nodeToSun[n.id] = randomSun.id
        sunSatellites[randomSun.id].push(n.id)
      }
    })

    // 5. Pre-compute initial positions for hierarchical layout
    const nodeCount = graphData.nodes.length
    const baseRadius = Math.max(510, Math.cbrt(nodeCount) * 85)  // 15% more compact overall

    // Calculate cluster sizes for proportional spacing
    const clusterSizes = {}
    suns.forEach(s => {
      clusterSizes[s.id] = 1 + sunSatellites[s.id].length
    })
    const maxClusterSize = Math.max(...Object.values(clusterSizes))

    // Position central sun at origin
    const sunPositions = {}
    sunPositions[centralSun.id] = { x: 0, y: 0, z: 0 }

    // Sort suns by cluster size (largest first) for weighted positioning
    const otherSuns = suns.filter(s => s.id !== centralSun.id)
    const sortedBySizeDesc = [...otherSuns].sort((a, b) => clusterSizes[b.id] - clusterSizes[a.id])

    // Calculate total "weight" - each cluster's angular area is proportional to its size
    const totalWeight = sortedBySizeDesc.reduce((sum, s) => sum + Math.sqrt(clusterSizes[s.id]), 0)

    // Base shell radius
    const sunShellRadius = baseRadius * 0.55

    // Golden ratio for Fibonacci-like distribution
    const goldenRatio = (1 + Math.sqrt(5)) / 2

    // Position suns using weighted Fibonacci - larger clusters get more angular space
    let cumulativeWeight = 0
    sortedBySizeDesc.forEach((sun, i) => {
      const clusterWeight = Math.sqrt(clusterSizes[sun.id])

      // Position based on cumulative weight (center of this cluster's angular slice)
      const weightPosition = (cumulativeWeight + clusterWeight / 2) / totalWeight
      cumulativeWeight += clusterWeight

      // Use golden angle but scale position by weight
      const theta = 2 * Math.PI * i / goldenRatio
      // Phi based on weighted position - larger clusters spread more evenly
      const phi = Math.acos(1 - 2 * weightPosition)

      // Larger clusters pushed slightly outward for more room
      const sizeRatio = clusterSizes[sun.id] / maxClusterSize
      const radiusAdjust = 0.9 + 0.2 * sizeRatio  // 0.9 to 1.1
      const adjustedRadius = sunShellRadius * radiusAdjust

      // Small jitter for organic feel
      const thetaJitter = (Math.random() - 0.5) * 0.08
      const phiJitter = (Math.random() - 0.5) * 0.05

      sunPositions[sun.id] = {
        x: adjustedRadius * Math.sin(phi + phiJitter) * Math.cos(theta + thetaJitter),
        y: adjustedRadius * Math.cos(phi + phiJitter),
        z: adjustedRadius * Math.sin(phi + phiJitter) * Math.sin(theta + thetaJitter)
      }
    })

    // Position satellites with normalized density across clusters
    const initialPositions = {}
    const clusterOrbitRadius = {}

    // Calculate target density: use median cluster size as reference
    const clusterSizeValues = Object.values(sunSatellites).map(s => s.length).filter(n => n > 0)
    const sortedSizes = [...clusterSizeValues].sort((a, b) => a - b)
    const medianSize = sortedSizes[Math.floor(sortedSizes.length / 2)] || 10

    // Target radius for median cluster - this sets the baseline density
    const medianRadius = 55
    // Density constant: for uniform density, r³/n should be constant
    // So r = k * n^(1/3), where k = medianRadius / medianSize^(1/3)
    const densityConstant = medianRadius / Math.cbrt(medianSize)

    suns.forEach(sun => {
      const sunPos = sunPositions[sun.id]
      initialPositions[sun.id] = sunPos

      const satellites = sunSatellites[sun.id]

      // Pure cube-root scaling for uniform density across all clusters
      // Minimum radius of 35 for single-satellite clusters
      const orbitRadius = Math.max(35, densityConstant * Math.cbrt(Math.max(satellites.length, 1)))
      clusterOrbitRadius[sun.id] = orbitRadius

      satellites.forEach((satId, idx) => {
        const goldenAngle = Math.PI * (3 - Math.sqrt(5))
        const theta = goldenAngle * idx
        const phi = Math.acos(1 - 2 * (idx + 0.5) / Math.max(satellites.length, 1))

        // Multi-shell distribution for larger clusters to spread nodes evenly
        // Small clusters: single shell, large clusters: up to 3 concentric shells
        const shellCount = satellites.length > 30 ? 3 : (satellites.length > 10 ? 2 : 1)
        const shellIndex = idx % shellCount
        const shellFactor = 0.7 + (shellIndex / Math.max(shellCount - 1, 1)) * 0.6  // Range: 0.7 to 1.3
        const adjustedRadius = orbitRadius * shellFactor

        // Moderate jitter for organic feel
        const jitter = 0.08
        const jx = (Math.random() - 0.5) * jitter * adjustedRadius
        const jy = (Math.random() - 0.5) * jitter * adjustedRadius
        const jz = (Math.random() - 0.5) * jitter * adjustedRadius

        initialPositions[satId] = {
          x: sunPos.x + adjustedRadius * Math.sin(phi) * Math.cos(theta) + jx,
          y: sunPos.y + adjustedRadius * Math.cos(phi) + jy,
          z: sunPos.z + adjustedRadius * Math.sin(phi) * Math.sin(theta) + jz
        }
      })
    })

    // Pre-compute edge types for visual hierarchy
    const edgeTypes = {}  // 'intra' = within cluster, 'inter' = between clusters
    graphData.links.forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source
      const targetId = typeof link.target === 'object' ? link.target.id : link.target
      const sourceSun = nodeToSun[sourceId]
      const targetSun = nodeToSun[targetId]
      const key = `${sourceId}->${targetId}`
      edgeTypes[key] = (sourceSun === targetSun) ? 'intra' : 'inter'
    })

    // Apply initial positions to nodes
    graphData.nodes.forEach(node => {
      const pos = initialPositions[node.id]
      if (pos) {
        node.fx = pos.x
        node.fy = pos.y
        node.fz = pos.z
      }
    })

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
              // Larger glow scales for more pop during traversal
              const glowScale = isPulsing ? 1.5 : (isFading ? 1.35 : (isTraversed ? 1.25 : 1.1))
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
        const initGlowScale = isPulsing ? 1.5 : (isFading ? 1.35 : (isTraversed ? 1.25 : 1.1))
        glow.scale.setScalar(needsGlow ? initGlowScale : 1.1)
        sphere.add(glow)

        // Cache the mesh
        nodeMeshCache.current.set(node.id, { sphere, glow })

        return sphere
      })
      .nodeLabel((node) => node.label)
      // Dynamic link coloring - both edge types visible for cohesive network
      .linkColor((link) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const reverseKey = `${targetId}->${sourceId}`

        // Traversed edges highlighted - 20% brighter
        if (traversedEdgesRef.current.has(edgeKey) || traversedEdgesRef.current.has(reverseKey)) {
          return 'rgba(31, 255, 234, 0.8)'
        }

        // Both edge types visible - inter-cluster slightly different color
        const isIntra = edgeTypes[edgeKey] === 'intra' || edgeTypes[reverseKey] === 'intra'
        if (isIntra) {
          return 'rgba(74, 107, 138, 0.45)'  // Blue-gray for intra-cluster
        }
        return 'rgba(90, 70, 110, 0.3)'  // Purple-tinted for inter-cluster connections
      })
      .linkWidth((link) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const reverseKey = `${targetId}->${sourceId}`

        if (traversedEdgesRef.current.has(edgeKey) || traversedEdgesRef.current.has(reverseKey)) {
          return 1.5  // Thicker for more pop
        }

        const isIntra = edgeTypes[edgeKey] === 'intra' || edgeTypes[reverseKey] === 'intra'
        return isIntra ? 0.5 : 0.35  // Inter-cluster edges visible but thinner
      })
      .linkOpacity(0.7)
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

    // ========== FORCES FOR 50% DENSITY CLUSTERS ==========
    // Visible cluster structure with network connectivity

    // Center force
    graph.d3Force('center', d3.forceCenter(0, 0, 0).strength(0.015))

    // Charge force - repulsion proportional to cluster size
    // Larger clusters push harder to claim more space
    graph.d3Force('charge', d3.forceManyBody()
      .strength(node => {
        const isSun = sunSet.has(node.id)
        if (!isSun) return -10
        // Central sun pushes others to shell
        if (node.id === centralSun.id) return -280
        // Repulsion scales with cluster size (sqrt for balance)
        const sizeRatio = Math.sqrt(clusterSizes[node.id] / maxClusterSize)
        return -120 - 150 * sizeRatio  // Range: -120 to -270
      })
      .distanceMin(20)
      .distanceMax(baseRadius * 1.5)
    )

    // Custom force: size-weighted angular repulsion between suns
    // Larger clusters claim more angular space on the sphere
    const sunAngularRepulsion = () => {
      const sunNodes = graphData.nodes.filter(n => sunSet.has(n.id) && n.id !== centralSun.id)

      // Pre-compute target angular "radius" for each sun based on cluster size
      const sunAngularRadius = {}
      const totalSqrtSize = sunNodes.reduce((sum, n) => sum + Math.sqrt(clusterSizes[n.id]), 0)
      sunNodes.forEach(n => {
        // Each sun's angular territory is proportional to sqrt of its cluster size
        // Total solid angle of hemisphere is 2π, distribute proportionally
        sunAngularRadius[n.id] = Math.PI * Math.sqrt(clusterSizes[n.id]) / totalSqrtSize
      })

      return (alpha) => {
        const strength = alpha * 6

        for (let i = 0; i < sunNodes.length; i++) {
          const nodeA = sunNodes[i]
          if (nodeA.x === undefined) continue

          for (let j = i + 1; j < sunNodes.length; j++) {
            const nodeB = sunNodes[j]
            if (nodeB.x === undefined) continue

            // Calculate angular distance (dot product of unit vectors)
            const rA = Math.sqrt(nodeA.x * nodeA.x + nodeA.y * nodeA.y + nodeA.z * nodeA.z) || 1
            const rB = Math.sqrt(nodeB.x * nodeB.x + nodeB.y * nodeB.y + nodeB.z * nodeB.z) || 1

            const ux = nodeA.x / rA, uy = nodeA.y / rA, uz = nodeA.z / rA
            const vx = nodeB.x / rB, vy = nodeB.y / rB, vz = nodeB.z / rB

            const dot = ux * vx + uy * vy + uz * vz
            const angle = Math.acos(Math.max(-1, Math.min(1, dot)))

            // Target minimum angle = sum of both clusters' angular radii
            const targetAngle = sunAngularRadius[nodeA.id] + sunAngularRadius[nodeB.id]

            if (angle < targetAngle * 1.2) {  // Start pushing before overlap
              // Push strength proportional to how much they're overlapping
              const overlap = (targetAngle * 1.2 - angle) / targetAngle
              const pushStrength = strength * overlap

              // Push A away from B (tangent to sphere)
              const perpAx = (vx - dot * ux)
              const perpAy = (vy - dot * uy)
              const perpAz = (vz - dot * uz)
              const perpAMag = Math.sqrt(perpAx * perpAx + perpAy * perpAy + perpAz * perpAz) || 1

              // Weight push by relative cluster sizes - smaller one moves more
              const totalSize = clusterSizes[nodeA.id] + clusterSizes[nodeB.id]
              const weightA = clusterSizes[nodeB.id] / totalSize  // A moves more if B is bigger
              const weightB = clusterSizes[nodeA.id] / totalSize

              nodeA.vx -= pushStrength * weightA * perpAx / perpAMag
              nodeA.vy -= pushStrength * weightA * perpAy / perpAMag
              nodeA.vz -= pushStrength * weightA * perpAz / perpAMag

              // Push B away from A
              const perpBx = (ux - dot * vx)
              const perpBy = (uy - dot * vy)
              const perpBz = (uz - dot * vz)
              const perpBMag = Math.sqrt(perpBx * perpBx + perpBy * perpBy + perpBz * perpBz) || 1

              nodeB.vx -= pushStrength * weightB * perpBx / perpBMag
              nodeB.vy -= pushStrength * weightB * perpBy / perpBMag
              nodeB.vz -= pushStrength * weightB * perpBz / perpBMag
            }
          }
        }
      }
    }
    graph.d3Force('sunSpacing', sunAngularRepulsion())

    // Link force - normalized distances based on cluster orbit radii
    graph.d3Force('link')
      .distance(link => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const isIntra = edgeTypes[edgeKey] === 'intra' || edgeTypes[`${targetId}->${sourceId}`] === 'intra'

        const sourceIsSun = sunSet.has(sourceId)
        const targetIsSun = sunSet.has(targetId)

        if (!isIntra) {
          // Inter-cluster: moderate distance
          return 130
        }

        if (sourceIsSun || targetIsSun) {
          // Sun-to-satellite: use normalized orbit radius for this cluster
          const sunId = sourceIsSun ? sourceId : targetId
          return clusterOrbitRadius[sunId] * 0.65  // 65% of orbit radius
        }
        // Satellite-to-satellite within cluster - scale with cluster orbit
        const clusterSunId = nodeToSun[sourceId]
        const radius = clusterOrbitRadius[clusterSunId] || 50
        return radius * 0.4  // 40% of orbit radius for intra-cluster satellite links
      })
      .strength(link => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const edgeKey = `${sourceId}->${targetId}`
        const isIntra = edgeTypes[edgeKey] === 'intra' || edgeTypes[`${targetId}->${sourceId}`] === 'intra'

        // Stronger pull within clusters
        return isIntra ? 0.7 : 0.15
      })

    // Collision force
    graph.d3Force('collision', d3.forceCollide()
      .radius(node => {
        const isSun = sunSet.has(node.id)
        return isSun ? 20 : 10
      })
      .strength(0.7)
      .iterations(1)
    )

    // Radial force - larger clusters slightly further out for breathing room
    graph.d3Force('sphereShape', d3.forceRadial(
      node => {
        const isSun = sunSet.has(node.id)
        if (isSun) {
          if (node.id === centralSun.id) return 0
          // Larger clusters pushed slightly outward
          const sizeRatio = clusterSizes[node.id] / maxClusterSize
          return sunShellRadius * (0.9 + 0.2 * sizeRatio)
        } else {
          // Satellites: positioned relative to their sun
          const sunId = nodeToSun[node.id]
          const sunPos = sunPositions[sunId]
          if (!sunPos || sunId === centralSun.id) {
            return (clusterOrbitRadius[sunId] || 50) * 0.6
          }
          const sunSizeRatio = clusterSizes[sunId] / maxClusterSize
          const sunRadius = sunShellRadius * (0.9 + 0.2 * sunSizeRatio)
          return sunRadius + (clusterOrbitRadius[sunId] || 50) * 0.4
        }
      },
      0, 0, 0
    ).strength(node => {
      return sunSet.has(node.id) ? 0.45 : 0.12
    }))

    // Disable unused forces
    graph.d3Force('radial', null)
    graph.d3Force('sunRadial', null)
    graph.d3Force('spherical', null)
    graph.d3Force('shells', null)
    graph.d3Force('cluster', null)

    // Simulation tuning
    graph.d3AlphaDecay(0.03)
    graph.d3VelocityDecay(0.4)
    graph.warmupTicks(120)
    graph.cooldownTicks(0)

    // Release fixed positions for organic settling
    setTimeout(() => {
      graphData.nodes.forEach(node => {
        delete node.fx
        delete node.fy
        delete node.fz
      })
      if (graphRef.current) {
        graphRef.current.d3ReheatSimulation()
        setTimeout(() => {
          if (graphRef.current) {
            // Reduce forces for stable state but keep spherical shape strong
            graph.d3Force('charge').strength(node => {
              const isSun = sunSet.has(node.id)
              return isSun ? -120 : -8
            })
            // Keep sphereShape force to maintain overall spherical structure
            graph.d3Force('sphereShape').strength(node => {
              return sunSet.has(node.id) ? 0.35 : 0.12
            })
          }
        }, 3000)
      }
    }, 800)

    // Set graph data
    graph.graphData(graphData)

    // Store reference
    graphRef.current = graph

    // Set initial camera position to view the full spherical structure
    const cameraDistance = baseRadius * 2.4  // Slightly further for compacted structure
    setTimeout(() => {
      graph.cameraPosition(
        { x: cameraDistance * 0.5, y: cameraDistance * 0.6, z: cameraDistance * 0.65 },
        { x: 0, y: 0, z: 0 },
        0
      )
    }, 100)

    // Log layout stats for debugging
    console.log(`Solar system layout: ${suns.length} suns, central sun: ${centralSun.label} (deg=${nodeDegree[centralSun.id]})`)

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

  // Handle visibility changes - resize and refresh when becoming visible
  useEffect(() => {
    if (isVisible && graphRef.current && containerRef.current) {
      // Small delay to ensure container has correct dimensions after becoming visible
      const timer = setTimeout(() => {
        if (containerRef.current && graphRef.current) {
          graphRef.current
            .width(containerRef.current.clientWidth)
            .height(containerRef.current.clientHeight)
          graphRef.current.refresh()
        }
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [isVisible])

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

  // Clear traversal state immediately when user sends a new query
  useEffect(() => {
    if (queryGeneration > 0) {
      setTraversedNodes(new Set())
      setTraversedEdges(new Set())
      setPulsingNodes(new Set())
      traversedNodesRef.current = new Set()
      traversedEdgesRef.current = new Set()
      pulsingNodesRef.current = new Set()
    }
  }, [queryGeneration])

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
      family_history: 'Family History',
      disease_reference: 'Disease Reference',
    }
    return types[type] || type
  }

  // Style for hiding while maintaining dimensions
  const hiddenStyle = !isVisible ? {
    visibility: 'hidden',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    pointerEvents: 'none',
  } : {}

  return (
    <div className="graph-panel" style={hiddenStyle}>
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

export default memo(GraphPanel)
