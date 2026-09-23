"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls, Text } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { riskColor } from "@/lib/format";
import type { WarehouseRack, WarehouseShelf } from "@/lib/types";

export interface Selection {
  rackId: string;
  locationCode: string;
}

const SHELF_HEIGHT = 0.55;
const SHELF_GAP = 0.78;
const RACK_SPACING = 3.2;
const MAX_RACKS = 12;
const MAX_SHELVES = 7;

function Shelf({
  shelf,
  y,
  selected,
  onSelect,
  rackId,
}: {
  shelf: WarehouseShelf;
  y: number;
  selected: boolean;
  onSelect: (selection: Selection) => void;
  rackId: string;
}) {
  const color = useMemo(() => new THREE.Color(riskColor(shelf.risk_band)), [shelf.risk_band]);
  const empty = shelf.unit_count === 0;

  return (
    <group>
      {/* upright shelf plate */}
      <mesh
        position={[0, y, 0]}
        onClick={(event) => {
          event.stopPropagation();
          onSelect({ rackId, locationCode: shelf.location_code });
        }}
        onPointerOver={(event) => {
          event.stopPropagation();
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          document.body.style.cursor = "auto";
        }}
      >
        <boxGeometry args={[2.4, SHELF_HEIGHT, 1.4]} />
        <meshStandardMaterial
          color={empty ? "#334155" : color}
          emissive={selected ? color : "#000000"}
          emissiveIntensity={selected ? 0.6 : 0}
          metalness={0.15}
          roughness={0.65}
        />
      </mesh>

      {/* stock boxes sitting on the shelf, scaled by real unit count */}
      {!empty ? (
        <mesh position={[-0.45, y + SHELF_HEIGHT, 0]}>
          <boxGeometry args={[0.5, 0.35, 0.9]} />
          <meshStandardMaterial color={color} metalness={0.1} roughness={0.8} transparent opacity={0.85} />
        </mesh>
      ) : null}

      <Text
        position={[-1.32, y, 0]}
        rotation={[0, -Math.PI / 2, 0]}
        fontSize={0.17}
        color={empty ? "#64748B" : "#CBD5E1"}
        anchorX="center"
      >
        {shelf.unit_count === 0 ? `${shelf.location_code} · no data` : `${shelf.location_code} · ${shelf.total_units}u`}
      </Text>
    </group>
  );
}

function Rack({
  rack,
  x,
  selectedCode,
  onSelect,
}: {
  rack: WarehouseRack;
  x: number;
  selectedCode: string | null;
  onSelect: (selection: Selection) => void;
}) {
  const shelves = rack.shelves.slice(0, MAX_SHELVES);
  return (
    <group position={[x, 0, 0]}>
      {/* rack frame */}
      <mesh position={[0, (shelves.length * SHELF_GAP) / 2, -0.75]}>
        <boxGeometry args={[2.5, Math.max(shelves.length * SHELF_GAP, 1), 0.12]} />
        <meshStandardMaterial color="#1E293F" metalness={0.4} roughness={0.6} />
      </mesh>

      <Text position={[0, shelves.length * SHELF_GAP + 0.35, 0]} fontSize={0.26} color="#7DD3FC" anchorX="center">
        {rack.id}
      </Text>

      {shelves.map((shelf, index) => (
        <Shelf
          key={shelf.location_code}
          rackId={rack.id}
          shelf={shelf}
          y={index * SHELF_GAP}
          selected={selectedCode === shelf.location_code}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}

export default function WarehouseScene({
  racks,
  selected,
  onSelect,
}: {
  racks: WarehouseRack[];
  selected: Selection | null;
  onSelect: (selection: Selection) => void;
}) {
  const visible = racks.slice(0, MAX_RACKS);
  const offset = (visible.length - 1) / 2;

  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [0, 7, 15], fov: 45 }}
      gl={{ antialias: true, powerPreference: "low-power" }}
      onPointerMissed={() => undefined}
    >
      <color attach="background" args={["#0B0F17"]} />
      <fog attach="fog" args={["#0B0F17", 18, 34]} />

      <ambientLight intensity={0.55} />
      <directionalLight position={[8, 14, 10]} intensity={1.1} />
      <directionalLight position={[-10, 6, -8]} intensity={0.35} color="#4FACFE" />

      {/* floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.32, 0]}>
        <planeGeometry args={[60, 40]} />
        <meshStandardMaterial color="#0F1522" metalness={0.2} roughness={0.9} />
      </mesh>
      <gridHelper args={[60, 60, "#1E293F", "#151E2E"]} position={[0, -0.31, 0]} />

      {visible.map((rack, index) => (
        <Rack
          key={rack.id}
          rack={rack}
          x={(index - offset) * RACK_SPACING}
          selectedCode={selected?.locationCode ?? null}
          onSelect={onSelect}
        />
      ))}

      <OrbitControls
        enablePan
        enableZoom
        minDistance={6}
        maxDistance={40}
        maxPolarAngle={Math.PI / 2.15}
        target={[0, 1.6, 0]}
      />
    </Canvas>
  );
}
