

"use client";

import { useState } from "react";
import PartisanBar from "./PartisanBar";
import MediaDensity, { type OutletCoverage } from "./MediaDensity";

interface CoverageVisualizationProps {
  colorado: number;
  neutro: number;
  anticolorado: number;
  outlets: OutletCoverage[];
  domain: [number, number];
  bandwidth: number;
}

export default function CoverageVisualization({
  colorado,
  neutro,
  anticolorado,
  outlets,
  domain,
  bandwidth,
}: CoverageVisualizationProps) {

  const [view, setView] = useState<"bar" | "density">("bar");

  const buttonClass = (active: boolean) =>
    `rounded border px-2 py-1 transition-colors ${
      active
        ? "border-[#2e4c8c] bg-[#2e4c8c] text-white"
        : "border-gray-300 text-gray-500 hover:bg-gray-100"
    }`;

  return (
    <section className="w-full">

      {/* Header and toggle */}
      <div className="mb-2 flex items-center justify-between">
         <span className="text-lg font-medium text-[#ffffff]">
          Sesgo hacia el gobierno
        </span>
      

        <div className="flex gap-1">

          <button
            type="button"
            onClick={() => setView("bar")}
            className={buttonClass(view === "bar")}
            title="Gráfico de barras"
            aria-label="Gráfico de barras"
            aria-pressed={view === "bar"}
          >
            <svg width="20" height="16" viewBox="0 0 20 16"
              fill="currentColor">
              <rect x="1" y="5" width="7" height="6" />
              <rect x="9" y="5" width="4" height="6" />
              <rect x="14" y="5" width="5" height="6" />
            </svg>
          </button>

          <button
            type="button"
            onClick={() => setView("density")}
            className={buttonClass(view === "density")}
            title="Gráfico de densidad"
            aria-label="Gráfico de densidad"
            aria-pressed={view === "density"}
          >
            <svg width="20" height="16" viewBox="0 0 20 16"
              fill="currentColor">
              <path d="M1 14 C4 14 4 2 8 2
                       C11 2 10 11 13 10
                       C15 9 15 5 17 8
                       L19 14 Z" />
            </svg>
          </button>

        </div>
      </div>

      {/* Selected visualization */}
      {view === "bar" ? (
        <PartisanBar
          
          neutro={neutro}
          anticolorado={anticolorado}
          colorado={colorado}
        />
      ) : (
        <MediaDensity
          outlets={outlets}
          domain={domain}
          bandwidth={bandwidth}
        />
      )}

    </section>
  );
}
