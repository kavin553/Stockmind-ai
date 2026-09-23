"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AGENT_SHORT, moneyCompact, number, riskColor } from "@/lib/format";
import type { AgentKey } from "@/lib/types";

const AXIS = { stroke: "#475569", fontSize: 11 };
const GRID = "#1E293F";

const tooltipStyle = {
  backgroundColor: "#101725",
  border: "1px solid #2A3A56",
  borderRadius: 8,
  fontSize: 12,
  color: "#E2E8F0",
} as const;

export function DeadStockByCategoryBar({ data }: { data: { category: string; value: number }[] }) {
  if (!data.length) return <ChartEmpty />;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ left: 12, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" tick={AXIS} tickFormatter={(value: number) => moneyCompact(value)} />
        <YAxis type="category" dataKey="category" tick={AXIS} width={110} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => moneyCompact(value)} />
        <Bar dataKey="value" name="Dead stock value" fill="#4FACFE" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function AgingBucketsBar({ data }: { data: { bucket: string; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="bucket" tick={AXIS} />
        <YAxis tick={AXIS} allowDecimals={false} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => `${value} SKUs`} />
        <Bar dataKey="count" name="SKUs" fill="#00F2FE" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function StrategyDistributionPie({ data }: { data: { strategy: string; count: number }[] }) {
  if (!data.length) return <ChartEmpty hint="Run a recovery analysis to populate strategy distribution." />;
  const colors = ["#00F2FE", "#4FACFE", "#10B981", "#F59E0B", "#EF4444"];
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="strategy"
          innerRadius={52}
          outerRadius={86}
          paddingAngle={2}
          label={(entry: { strategy: string }) => AGENT_SHORT[entry.strategy as AgentKey] ?? entry.strategy}
        >
          {data.map((entry, index) => (
            <Cell key={entry.strategy} fill={colors[index % colors.length]} stroke="#0B0F17" />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => `${value} cases`} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function CapitalAtRiskLine({ data }: { data: { label: string; value: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <defs>
          <linearGradient id="capitalFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#EF4444" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#EF4444" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="label" tick={AXIS} />
        <YAxis tick={AXIS} tickFormatter={(value: number) => moneyCompact(value)} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => moneyCompact(value)} />
        <Area type="monotone" dataKey="value" name="Capital at risk" stroke="#EF4444" fill="url(#capitalFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ForecastVsActualLine({ data }: { data: { label: string; forecast: number; actual: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="label" tick={AXIS} />
        <YAxis tick={AXIS} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94A3B8" }} />
        <Line type="monotone" dataKey="forecast" name="Predicted (7d)" stroke="#4FACFE" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="actual" name="Actual units" stroke="#10B981" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function SalesTrendArea({ data }: { data: { date: string; quantity: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <defs>
          <linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00F2FE" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#00F2FE" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="date" tick={AXIS} minTickGap={30} />
        <YAxis tick={AXIS} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => `${value} units`} />
        <Area type="monotone" dataKey="quantity" name="Units sold" stroke="#00F2FE" fill="url(#salesFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RecoveryComparisonBar({ data }: { data: { name: string; gross: number; net: number }[] }) {
  if (!data.length) return <ChartEmpty />;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" tick={AXIS} />
        <YAxis tick={AXIS} tickFormatter={(value: number) => moneyCompact(value)} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => moneyCompact(value)} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94A3B8" }} />
        <Bar dataKey="gross" name="Expected recovery" fill="#4FACFE" radius={[4, 4, 0, 0]} />
        <Bar dataKey="net" name="Expected net recovery" fill="#00F2FE" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function InventoryValueBar({ data }: { data: { name: string; value: number; band: string }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ left: 4, right: 8, top: 4, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" tick={AXIS} />
        <YAxis tick={AXIS} tickFormatter={(value: number) => moneyCompact(value)} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value: number) => moneyCompact(value)} />
        <Bar dataKey="value" name="Inventory value" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={riskColor(entry.band as never)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function ChartEmpty({ hint }: { hint?: string }) {
  return (
    <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-base-600 text-xs text-slate-500">
      {hint ?? "No data available for this chart yet."}
    </div>
  );
}

export { number };
