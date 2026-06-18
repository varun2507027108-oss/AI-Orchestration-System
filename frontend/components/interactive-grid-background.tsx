"use client";

import React, { useEffect, useRef, useState } from "react";

export function InteractiveGridBackground() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isTouchOrReducedMotion, setIsTouchOrReducedMotion] = useState(true);

  useEffect(() => {
    const mediaQueryReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mediaQueryTouch = window.matchMedia("(hover: none)");

    const checkSettings = () => {
      setIsTouchOrReducedMotion(mediaQueryReduced.matches || mediaQueryTouch.matches);
    };

    checkSettings();

    mediaQueryReduced.addEventListener("change", checkSettings);
    mediaQueryTouch.addEventListener("change", checkSettings);

    return () => {
      mediaQueryReduced.removeEventListener("change", checkSettings);
      mediaQueryTouch.removeEventListener("change", checkSettings);
    };
  }, []);

  useEffect(() => {
    if (isTouchOrReducedMotion) return;

    const container = containerRef.current;
    if (!container) return;

    const parent = container.parentElement;
    if (!parent) return;

    // Set initial custom property values off-screen
    parent.style.setProperty("--mx", "-9999px");
    parent.style.setProperty("--my", "-9999px");

    let frameId: number | null = null;

    const handleMouseMove = (e: MouseEvent) => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }

      frameId = requestAnimationFrame(() => {
        const rect = parent.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        parent.style.setProperty("--mx", `${x}px`);
        parent.style.setProperty("--my", `${y}px`);
      });
    };

    const handleMouseLeave = () => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }
      frameId = requestAnimationFrame(() => {
        parent.style.setProperty("--mx", "-9999px");
        parent.style.setProperty("--my", "-9999px");
      });
    };

    parent.addEventListener("mousemove", handleMouseMove);
    parent.addEventListener("mouseleave", handleMouseLeave);

    return () => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }
      parent.removeEventListener("mousemove", handleMouseMove);
      parent.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [isTouchOrReducedMotion]);

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 pointer-events-none z-0 overflow-hidden"
    >
      {/* Layer 1: Static dim grid */}
      <div className="absolute inset-0 opacity-[0.08] text-border-subtle dark:opacity-[0.06]">
        <GridSvg />
      </div>

      {/* Layer 2: Glowing accent grid */}
      {!isTouchOrReducedMotion && (
        <div
          className="absolute inset-0 opacity-40 text-accent transition-opacity duration-300"
          style={{
            maskImage:
              "radial-gradient(circle 300px at var(--mx, -9999px) var(--my, -9999px), black 0%, rgba(0, 0, 0, 0.4) 50%, transparent 100%)",
            WebkitMaskImage:
              "radial-gradient(circle 300px at var(--mx, -9999px) var(--my, -9999px), black 0%, rgba(0, 0, 0, 0.4) 50%, transparent 100%)",
          }}
        >
          <GridSvg />
        </div>
      )}
    </div>
  );
}

function GridSvg() {
  return (
    <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern
          id="blueprint-grid"
          width="56"
          height="56"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M 56 0 L 0 0 0 56"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#blueprint-grid)" />
    </svg>
  );
}
