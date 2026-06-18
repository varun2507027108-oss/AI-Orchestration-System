"use client";

import { useTheme } from "@/components/theme-provider";
import { useEffect, useState } from "react";
import { AnimatedThemeToggler, TransitionVariant } from "@/components/ui/animated-theme-toggler";

export function CustomThemeToggler({ variant = "circle" }: { variant?: TransitionVariant }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-8 h-8" />;
  }

  return (
    <AnimatedThemeToggler
      theme={resolvedTheme}
      onThemeChange={(t) => setTheme(t)}
      variant={variant}
    />
  );
}