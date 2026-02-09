"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface Stat {
  value: string;
  label: string;
  isNumeric: boolean;
  target?: number;
}

const STATS: Stat[] = [
  { value: "2,847", label: "Games Played", isNumeric: true, target: 2847 },
  { value: "Poker", label: "Now Playing", isNumeric: false },
  { value: "30s", label: "Per Turn", isNumeric: false },
  { value: "24/7", label: "Live", isNumeric: false },
];

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function StatItem({ stat, visible }: { stat: Stat; visible: boolean }) {
  const [count, setCount] = useState(0);

  const animate = useCallback(() => {
    if (!stat.isNumeric || !stat.target || !visible) return;

    const duration = 1800;
    const target = stat.target;
    const start = performance.now();

    const step = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * target));
      if (progress < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  }, [stat.isNumeric, stat.target, visible]);

  useEffect(() => {
    animate();
  }, [animate]);

  return (
    <div className="flex flex-col items-center gap-2 px-6 py-4">
      <span className="font-display text-4xl font-black text-gold sm:text-5xl">
        {stat.isNumeric && visible ? formatNumber(count) : stat.value}
      </span>
      <span className="font-headline text-xs tracking-[0.3em] text-mc-white/50">
        {stat.label.toUpperCase()}
      </span>
    </div>
  );
}

export function Stats() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.3 },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section ref={ref} className="relative overflow-hidden py-16">
      {/* Gold accent lines */}
      <div className="absolute top-0 right-0 left-0 h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" />
      <div className="absolute right-0 bottom-0 left-0 h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent" />

      <div className="mx-auto max-w-5xl px-6">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {STATS.map((stat) => (
            <StatItem key={stat.label} stat={stat} visible={visible} />
          ))}
        </div>
      </div>
    </section>
  );
}
