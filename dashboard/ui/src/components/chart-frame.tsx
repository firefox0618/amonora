"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type ChartSize = {
  width: number;
  height: number;
};

export function ChartFrame({
  className,
  chartClassName,
  minHeight = 240,
  children,
}: {
  className?: string;
  chartClassName?: string;
  minHeight?: number;
  children: (size: ChartSize) => ReactNode;
}) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<ChartSize>({ width: 0, height: 0 });

  useEffect(() => {
    const node = frameRef.current;
    if (!node) {
      return;
    }

    const syncSize = () => {
      const nextWidth = Math.max(0, Math.floor(node.clientWidth));
      const nextHeight = Math.max(0, Math.floor(node.clientHeight));
      setSize((previous) => {
        if (previous.width === nextWidth && previous.height === nextHeight) {
          return previous;
        }
        return { width: nextWidth, height: nextHeight };
      });
    };

    syncSize();
    const observer = new ResizeObserver(() => syncSize());
    observer.observe(node);
    window.addEventListener("resize", syncSize);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", syncSize);
    };
  }, []);

  const isReady = size.width > 0 && size.height > 0;

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div
        ref={frameRef}
        className={cn("relative min-h-0 flex-1 overflow-hidden rounded-[22px]", chartClassName)}
        style={{ minHeight }}
      >
        {isReady ? (
          children(size)
        ) : (
          <div className="control-grid h-full w-full animate-pulse rounded-[22px] bg-[var(--surface-muted)]" />
        )}
      </div>
    </div>
  );
}
