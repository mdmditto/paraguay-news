"use client";

import { useId } from "react";

export type OutletCoverage = {
  source: string;
  pc1: number;
  n_articles: number;
};

type Props = {
  outlets: OutletCoverage[];
  domain: [number, number];
  bandwidth: number;
};

export default function MediaDensity({
  outlets,
  domain,
  bandwidth,
}: Props) {
  const gradientId = useId();

  const width = 400;
  const height = 130;

  const margin = {
    top: 10,
    right: 12,
    bottom: 12,
    left: 12,
  };

  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  // Symmetric domain around zero so the vertical line stays centered
  const maxAbs = Math.max(
    Math.abs(domain[0]),
    Math.abs(domain[1])
  );

  const xMin = -maxAbs;
  const xMax = maxAbs;

  const validOutlets = outlets.filter(
    (d) =>
      Number.isFinite(d.pc1) &&
      Number.isFinite(d.n_articles) &&
      d.n_articles > 0
  );

  if (
    validOutlets.length === 0 ||
    !Number.isFinite(bandwidth) ||
    bandwidth <= 0 ||
    !Number.isFinite(maxAbs) ||
    maxAbs <= 0
  ) {
    return (
      <p className="text-xs text-gray-500">
        Datos insuficientes para estimar la distribución.
      </p>
    );
  }

  const gaussian = (x: number, mu: number) => {
    const z = (x - mu) / bandwidth;
    return (
      Math.exp(-0.5 * z * z) /
      (bandwidth * Math.sqrt(2 * Math.PI))
    );
  };

  const points = Array.from({ length: 250 }, (_, i) => {
    const x = xMin + (i / 249) * (xMax - xMin);

    const y = validOutlets.reduce(
      (sum, outlet) =>
        sum + outlet.n_articles * gaussian(x, outlet.pc1),
      0
    );

    return { x, y };
  });

  const yMax = Math.max(...points.map((p) => p.y)) * 1.15;

  const xScale = (x: number) =>
    margin.left +
    ((x - xMin) / (xMax - xMin)) * plotWidth;

  const yScale = (y: number) =>
    margin.top +
    plotHeight -
    (y / yMax) * plotHeight;

  const baseline = yScale(0);

  const linePath = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"} ${xScale(p.x)} ${yScale(p.y)}`
    )
    .join(" ");

  const areaPath = `
    ${linePath}
    L ${xScale(xMax)} ${baseline}
    L ${xScale(xMin)} ${baseline}
    Z
  `;

  const totalArticles = validOutlets.reduce(
    (sum, d) => sum + d.n_articles,
    0
  );

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label="Distribución de la cobertura mediática"
      >
        <defs>
          <linearGradient
            id={gradientId}
            gradientUnits="userSpaceOnUse"
            x1={xScale(xMin)}
            y1={0}
            x2={xScale(xMax)}
            y2={0}
          >
            <stop offset="0%" stopColor="#2e4c8c" />
            <stop offset="46%" stopColor="#2e4c8c" />
            <stop offset="50%" stopColor="#ffffff" />
            <stop offset="54%" stopColor="#fa2d1a" />
            <stop offset="100%" stopColor="#fa2d1a" />
          </linearGradient>
        </defs>

        {/* Density area */}
        <path
          d={areaPath}
          fill={`url(#${gradientId})`}
          fillOpacity={0.85}
        />

        {/* Density outline */}
        <path
          d={linePath}
          fill="none"
          stroke="#333333"
          strokeWidth={1}
          strokeLinejoin="round"
        />

        {/* Center vertical line */}
        <line
          x1={xScale(0)}
          x2={xScale(0)}
          y1={margin.top}
          y2={baseline}
          stroke="#888888"
          strokeWidth={1}
          strokeDasharray="4 4"
        />

        {/* Horizontal axis */}
        <line
          x1={margin.left}
          x2={width - margin.right}
          y1={baseline}
          y2={baseline}
          stroke="#999999"
          strokeWidth={1}
        />

        {/* Outlet points */}
        {validOutlets.map((outlet) => (
          <circle
            key={outlet.source}
            cx={xScale(outlet.pc1)}
            cy={baseline}
            r={Math.sqrt(outlet.n_articles) * 2.5}
            fill={outlet.pc1 < 0 ? "#2e4c8c" : "#fa2d1a"}
            stroke="#FFFFFF"
            strokeWidth={1}
            className="cursor-pointer"
          >
            <title>
              {outlet.source}
              {`\nArtículos: ${outlet.n_articles}`}
              {`\nPC1: ${outlet.pc1.toFixed(3)}`}
            </title>
          </circle>
        ))}

        {/* Labels INSIDE the graph */}
        <text
          x={margin.left}
          y={baseline - 6}
          fontSize="20"
          font-weight="bold"
          fill="#2e4c8c"
        >
          Crítico
        </text>

        <text
          x={width - margin.right}
          y={baseline - 6}
          fontSize="20"
          font-weight="bold"
          textAnchor="end"
          fill="#fa2d1a"
        >
          Pro
        </text>
      </svg>

    </div>
  );
}
