// Agent state from 000h by Cojeev — MIT licence — docs, variants and the full library: https://cojeev.com/ui/docs/agent-state/
"use client";

import * as React from "react";
import { useSyncExternalStore } from "react";
import { type ClassValue, clsx } from "clsx";
import type { Transition } from "motion";
import { motion, useInView } from "motion/react";
import { twMerge } from "tailwind-merge";

// ---- registry/cojeev/lib/utils.ts (inlined) ----
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ---- registry/cojeev/motion/settings.ts (inlined) ----
const RUNTIME = {
  cfg: {
    rest: false,
    reach: true,
    merge: true,
    hold: true,
    jiggleOn: true,
    press: true,
    echo: false,
    dots: 0,
    grain: 0.08,
    sheen: 0.6,
    curve: 1.2,
    lobeK: 130,
    lobeZ: 1,
    mergeZ: 0.8,
    arcK: 40,
    holdK: 80,
    pressK: 170,
    jiggle: 0.35,
    jiggleDecay: 1.6,
    restSpeed: 1,
    drift: 1,
    quality: 2.5,
  },
  tier: {
    pill: { amp: 0, reach: 3, inside: 1.2, press: 0.02 },
    tile: { amp: 0, reach: 2.4, inside: 1, press: 0.02 },
    nav: { amp: 0, reach: 1.2, inside: 0.5, press: 0.008 },
    card: { amp: 0, reach: 1, inside: 0.4, press: 0.004 },
    blob: { amp: 0.006, reach: 3, inside: 1.2, press: 0.03 },
  },
};
const factoryTiers = {
  pill: {
    amp: 0.008,
    reach: 4,
    inside: 2,
    sig: 24,
    R: 80,
    press: 0.03,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
  tile: {
    amp: 0.008,
    reach: 3.5,
    inside: 1.6,
    sig: 18,
    R: 64,
    press: 0.035,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
  nav: {
    amp: 0.0006,
    reach: 3,
    inside: 1.2,
    sig: 24,
    R: 64,
    press: 0.01,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
  card: {
    amp: 0.0003,
    reach: 2.5,
    inside: 0.9,
    sig: 44,
    R: 56,
    press: 0.004,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
  blob: {
    amp: 0.012,
    reach: 4,
    inside: 1.8,
    sig: 22,
    R: 64,
    press: 0.05,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
  spinner: {
    amp: 0.14,
    reach: 0,
    inside: 0,
    sig: 1,
    R: 0,
    press: 0,
    lobes: 0,
    depth: 0,
    asym: 0,
    spread: 0.55,
  },
};
const factoryCfg = {
  quality: 2.5,
  grain: 0.12,
  sheen: 1,
  curve: 1,
  lobeK: 90,
  lobeZ: 0.9,
  mergeZ: 0.62,
  arcK: 26,
  holdK: 55,
  pressK: 140,
  jiggle: 0.45,
  jiggleDecay: 1.35,
  restSpeed: 1,
  drift: 1,
  rest: true,
  reach: true,
  merge: true,
  hold: true,
  jiggleOn: true,
  press: true,
  echo: false,
  echoOff: 6,
  echoScale: 1.04,
  dots: 0,
};
type MorphConfig = typeof factoryCfg;
type TierName = keyof typeof factoryTiers;
type Tier = typeof factoryTiers.pill;
type ProductCategory = "buttons" | "icons" | "pills" | "cards" | "skeleton";
type Category = ProductCategory | "nav" | "inputs" | "controls" | "surfaces";
type MotionSettings = {
  v: 3;
  mode: "off" | "subtle";
  cats: Record<Category, boolean>;
};
type MorphProfile = { cfg: MorphConfig; TIER: Record<TierName, Tier> };
type FlowVariant =
  | "glide"
  | "stretch"
  | "jelly"
  | "comet"
  | "drop"
  | "rubber"
  | "pebble"
  | "ripple"
  | "halo"
  | "off";
type FlowSettings = {
  variant: FlowVariant;
  hover: boolean;
  speed: number;
  intensity: number;
  hoverStrength: number;
};
type SettingsSnapshot = Readonly<{
  motion: MotionSettings;
  flow: FlowSettings;
  profile: MorphProfile;
  authored: boolean;
}>;
const MOTION_KEY = "v-motion";
const MORPH_KEY = "v-morph-cfg-v3";
const FLOW_KEY = "v-flow-v1";
const PRODUCT_CATEGORIES: readonly ProductCategory[] = [
  "buttons",
  "icons",
  "pills",
  "cards",
  "skeleton",
];
const FLOW_DEFAULTS: Readonly<FlowSettings> = Object.freeze({
  variant: "glide",
  hover: true,
  speed: 1,
  intensity: 1,
  hoverStrength: 1,
});
const FLOW_CHARACTERS: Record<
  FlowVariant,
  { label: string; duration: number; ease: string; land: string; glow?: string }
> = {
  glide: {
    label: "Glide",
    duration: 0.24,
    ease: "cubic-bezier(.2,.8,.2,1)",
    land: "none",
  },
  stretch: {
    label: "Stretch",
    duration: 0.3,
    ease: "cubic-bezier(.3,1.15,.4,1)",
    land: "vf-land",
  },
  jelly: {
    label: "Jelly",
    duration: 0.5,
    ease: "cubic-bezier(.3,1.3,.45,1)",
    land: "vf-jellyx",
  },
  comet: {
    label: "Comet",
    duration: 0.34,
    ease: "cubic-bezier(.2,.8,.2,1)",
    land: "vf-land",
  },
  drop: {
    label: "Ink drop",
    duration: 0.3,
    ease: "cubic-bezier(.3,1.25,.4,1)",
    land: "vf-bloom",
  },
  rubber: {
    label: "Rubber",
    duration: 0.36,
    ease: "cubic-bezier(.3,1.3,.4,1)",
    land: "vf-land",
  },
  pebble: {
    label: "Pebble",
    duration: 0.46,
    ease: "cubic-bezier(.32,1.25,.42,1)",
    land: "vf-lean",
  },
  ripple: {
    label: "Ripple",
    duration: 0.36,
    ease: "cubic-bezier(.2,.8,.2,1)",
    land: "vf-land",
    glow: "vf-ring",
  },
  halo: {
    label: "Halo",
    duration: 0.4,
    ease: "cubic-bezier(.3,1.2,.4,1)",
    land: "vf-land",
    glow: "vf-glow",
  },
  off: { label: "Off", duration: 0, ease: "linear", land: "none" },
};
const defaultSettings: MotionSettings = {
  v: 3,
  mode: "subtle",
  cats: {
    buttons: true,
    icons: true,
    pills: true,
    cards: false,
    skeleton: true,
    nav: false,
    inputs: false,
    controls: false,
    surfaces: false,
  },
};
function runtime(): MorphProfile {
  const TIER = structuredClone(factoryTiers);
  for (const name of Object.keys(RUNTIME.tier) as (keyof typeof RUNTIME.tier)[])
    Object.assign(TIER[name], RUNTIME.tier[name]);
  return { cfg: { ...factoryCfg, ...RUNTIME.cfg }, TIER };
}
function immutable<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value).forEach(immutable);
    Object.freeze(value);
  }
  return value;
}
const serverSnapshot: SettingsSnapshot = immutable({
  motion: structuredClone(defaultSettings),
  flow: { ...FLOW_DEFAULTS },
  profile: runtime(),
  authored: false,
});
let settings = structuredClone(defaultSettings),
  profile = runtime(),
  flow = { ...FLOW_DEFAULTS },
  authored = false,
  loaded = false;
let snapshot = serverSnapshot;
const listeners = new Set<() => void>();
let releaseEvents: undefined | (() => void),
  dispatching = false;
function storage() {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
function parse(key: string): unknown {
  try {
    return JSON.parse(storage()?.getItem(key) || "null");
  } catch {
    return null;
  }
}
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function mergeProfile(
  value: unknown,
  base: MorphProfile,
  strict = false,
): MorphProfile {
  if (!record(value) || (!record(value.cfg) && !record(value.TIER)))
    throw new Error("Profile must contain a cfg or TIER object.");
  const next = structuredClone(base);
  if (record(value.cfg))
    for (const key of Object.keys(next.cfg) as (keyof MorphConfig)[]) {
      const v = value.cfg[key];
      if (v === undefined) continue;
      if (
        typeof v !== typeof next.cfg[key] ||
        (typeof v === "number" && !Number.isFinite(v))
      ) {
        if (strict)
          throw new Error(
            `Invalid cfg.${key}: expected a finite ${typeof next.cfg[key]}.`,
          );
        continue;
      }
      Object.assign(next.cfg, { [key]: v });
    }
  if (record(value.TIER))
    for (const name of Object.keys(next.TIER) as TierName[]) {
      const saved = value.TIER[name];
      if (!record(saved)) continue;
      for (const key of Object.keys(next.TIER[name]) as (keyof Tier)[]) {
        const v = saved[key];
        if (v === undefined) continue;
        if (typeof v !== "number" || !Number.isFinite(v)) {
          if (strict)
            throw new Error(
              `Invalid TIER.${name}.${key}: expected a finite number.`,
            );
          continue;
        }
        next.TIER[name][key] = v;
      }
    }
  return next;
}
function normalizeFlow(value: unknown): FlowSettings {
  const v = record(value) ? value : {},
    number = (key: string, fallback: number, min: number) =>
      typeof v[key] === "number" && Number.isFinite(v[key])
        ? Math.max(min, v[key] as number)
        : fallback;
  return {
    variant:
      typeof v.variant === "string" && Object.hasOwn(FLOW_CHARACTERS, v.variant)
        ? (v.variant as FlowVariant)
        : "glide",
    hover: typeof v.hover === "boolean" ? v.hover : true,
    speed: number("speed", 1, 0.25),
    intensity: number("intensity", 1, 0),
    hoverStrength: number("hoverStrength", 1, 0),
  };
}
function flowToken(name: string, fallback: string, el?: Element) {
  try {
    return (
      getComputedStyle(el ?? document.documentElement)
        .getPropertyValue(name)
        .trim() || fallback
    );
  } catch {
    return fallback;
  }
}
function flowTokenMs(name: string, fallback: number, el?: Element) {
  const v = flowToken(name, "", el),
    n = parseFloat(v);
  return Number.isFinite(n) ? n * (v.endsWith("ms") ? 1 : 1000) : fallback;
}
function applyFlowSettings() {
  if (typeof document === "undefined") return;
  const h = document.documentElement,
    variant = settings.mode === "off" ? "off" : flow.variant,
    c = FLOW_CHARACTERS[variant],
    hover = flow.hover ? "on" : "off";
  // Read the character tokens before any root write: a computed read after one forces a
  // whole-document style pass. Unchanged writes are skipped, as they still wake every observer.
  const values: Record<string, string> = {
    "--flow-speed": String(flow.speed),
    "--flow-intensity": String(flow.intensity),
    "--flow-hover": String(flow.hoverStrength),
    "--flow-ease":
      variant === "off" ? c.ease : flowToken("--e-flow-" + variant, c.ease),
    "--flow-dur":
      (
        (variant === "off"
          ? 0
          : flowTokenMs("--t-flow-" + variant, c.duration * 1000)) /
        1000 /
        flow.speed
      ).toFixed(3) + "s",
    "--flow-land": c.land,
    "--flow-glow": c.glow || "none",
  };
  if (h.dataset.flow !== variant) h.dataset.flow = variant;
  if (h.dataset.flowHover !== hover) h.dataset.flowHover = hover;
  for (const [name, value] of Object.entries(values))
    if (h.style.getPropertyValue(name) !== value)
      h.style.setProperty(name, value);
}
function publish() {
  const next = { motion: settings, flow, profile, authored };
  if (JSON.stringify(next) === JSON.stringify(snapshot)) {
    applyFlowSettings();
    return;
  }
  snapshot = immutable(structuredClone(next));
  applyFlowSettings();
  listeners.forEach((fn) => fn());
}
function loadMotionSettings() {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  settings = structuredClone(defaultSettings);
  profile = runtime();
  flow = { ...FLOW_DEFAULTS };
  authored = false;
  const raw = parse(MOTION_KEY);
  if (record(raw)) {
    if (raw.mode === "off" || raw.mode === "subtle") settings.mode = raw.mode;
    if (raw.v === 3 && record(raw.cats))
      for (const key of PRODUCT_CATEGORIES)
        if (typeof raw.cats[key] === "boolean")
          settings.cats[key] = raw.cats[key];
  }
  flow = normalizeFlow(parse(FLOW_KEY));
  const saved = parse(MORPH_KEY);
  if (saved)
    try {
      profile = mergeProfile(saved, {
        cfg: { ...factoryCfg },
        TIER: structuredClone(factoryTiers),
      });
      authored = true;
    } catch {
      /* Corrupt saved data keeps a usable runtime. */
    }
  try {
    for (const key of [
      "v-alive-settings",
      "v-morph-cfg",
      "v-morph-cfg-v2",
      "v-motion-cfg",
    ])
      storage()?.removeItem(key);
  } catch {}
  publish();
}
function getMotionSettings() {
  loadMotionSettings();
  return structuredClone(settings);
}
function getFlowSettings() {
  loadMotionSettings();
  return { ...flow };
}
function getSettingsSnapshot() {
  loadMotionSettings();
  return snapshot;
}
function getServerSettingsSnapshot() {
  return serverSnapshot;
}
function reloadMotionSettings() {
  loaded = false;
  loadMotionSettings();
}
function acquireEvents() {
  if (releaseEvents || typeof window === "undefined") return;
  const onStorage = (event: StorageEvent) => {
    if (
      event.key === null ||
      [MOTION_KEY, MORPH_KEY, FLOW_KEY].includes(event.key)
    )
      reloadMotionSettings();
  };
  const onEngine = () => {
    if (!dispatching) reloadMotionSettings();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("v-motion-change", onEngine);
  window.addEventListener("v-flow", onEngine);
  releaseEvents = () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("v-motion-change", onEngine);
    window.removeEventListener("v-flow", onEngine);
    releaseEvents = undefined;
  };
}
function subscribeSettings(fn: () => void) {
  loadMotionSettings();
  listeners.add(fn);
  acquireEvents();
  return () => {
    listeners.delete(fn);
    if (!listeners.size) releaseEvents?.();
  };
}
function event(name: string) {
  if (typeof window === "undefined") return;
  dispatching = true;
  try {
    window.dispatchEvent(
      new CustomEvent(name, {
        detail: name === "v-flow" ? getFlowSettings() : getMotionSettings(),
      }),
    );
  } finally {
    dispatching = false;
  }
}

// ---- registry/cojeev/motion/use-reduced-motion.ts (inlined) ----
let query: MediaQueryList | undefined;
const listeners_UseReducedMotion = new Set<() => void>();
const changed = () =>
  listeners_UseReducedMotion.forEach((listener) => listener());
function media() {
  return (query ??= window.matchMedia("(prefers-reduced-motion: reduce)"));
}
function subscribe(listener: () => void) {
  const q = media();
  if (!listeners_UseReducedMotion.size) q.addEventListener("change", changed);
  listeners_UseReducedMotion.add(listener);
  return () => {
    listeners_UseReducedMotion.delete(listener);
    if (!listeners_UseReducedMotion.size) {
      q.removeEventListener("change", changed);
      query = undefined;
    }
  };
}
function snapshot_UseReducedMotion() {
  return typeof window === "undefined" ? false : media().matches;
}
const serverSnapshot_UseReducedMotion = () => false;
/** Dynamic accessibility preference shared by genuine in-progress indicators and other component roles. */
function useReducedMotion() {
  return useSyncExternalStore(
    subscribe,
    snapshot_UseReducedMotion,
    serverSnapshot_UseReducedMotion,
  );
}

// ---- registry/cojeev/motion/choreography.ts (inlined) ----
/** The shared rhythm. Durations and stagger are seconds, matching Motion's API. */
const motionTokens = {
  spring: {
    responsive: { type: "spring", stiffness: 360, damping: 32, mass: 0.85 },
    expressive: { type: "spring", stiffness: 260, damping: 22, mass: 1 },
    gentle: { type: "spring", stiffness: 180, damping: 28, mass: 1 },
  },
  ease: {
    enter: [0.2, 0.8, 0.2, 1],
    exit: [0.4, 0, 1, 1],
    settle: [0.2, 0.65, 0.25, 1],
  },
  duration: { quick: 0.16, enter: 0.32, exit: 0.18 },
  stagger: 0.035,
} as const;
const isQuiet = (snapshot: SettingsSnapshot) =>
  snapshot.motion.mode === "off" || snapshot.flow.variant === "off";
function resolveChoreography(
  snapshot: SettingsSnapshot,
  reduced: boolean,
): { quiet: boolean; transition: Transition } {
  const quiet = reduced || isQuiet(snapshot);
  if (quiet) return { quiet, transition: { duration: 0, delay: 0 } };
  const speed = snapshot.flow.speed;
  const spring = ["jelly", "rubber", "drop", "pebble"].includes(
    snapshot.flow.variant,
  )
    ? motionTokens.spring.expressive
    : motionTokens.spring.responsive;
  return {
    quiet,
    transition: {
      ...spring,
      stiffness: spring.stiffness * speed * speed,
      damping: spring.damping * speed,
    },
  };
}
/** Reactive settings subscription for reusable React surfaces. */
function useChoreography() {
  const snapshot = React.useSyncExternalStore(
    subscribeSettings,
    getSettingsSnapshot,
    getServerSettingsSnapshot,
  );
  const reduced = useReducedMotion();
  return React.useMemo(
    () => resolveChoreography(snapshot, reduced),
    [snapshot, reduced],
  );
}

// ---- registry/cojeev/ui/agent-state.tsx ----
export type AgentStatus =
  "idle" | "thinking" | "working" | "needs-input" | "complete" | "error";
export type AgentStateProps = Omit<React.ComponentProps<"div">, "children"> & {
  status?: AgentStatus;
  size?: "sm" | "md" | "lg";
  label?: string;
  description?: string;
};
const stateLabels: Record<AgentStatus, string> = {
  idle: "Ready when you are",
  thinking: "Thinking",
  working: "Working",
  "needs-input": "Your decision",
  complete: "Complete",
  error: "Needs attention",
};
// Equal cubic topology lets Motion interpolate a folded fluid silhouette without
// a second animation clock. Each state remains recognizable when motion is off.
const silhouettes: Record<AgentStatus, string> = {
  idle: "M90 24C116 17 151 32 153 60C157 84 139 96 124 116C111 135 81 141 59 126C34 113 22 85 32 61C43 36 65 31 90 24Z",
  thinking:
    "M90 18C120 27 132 19 148 51C163 78 141 92 135 116C127 146 94 137 68 129C40 123 18 98 30 70C40 48 66 7 90 18Z",
  working:
    "M90 17C114 11 156 41 151 65C146 85 165 110 134 123C106 140 85 121 61 131C34 140 17 94 30 71C44 47 68 25 90 17Z",
  "needs-input":
    "M90 27C121 20 147 29 145 61C143 82 162 111 134 125C108 138 91 114 65 127C35 140 28 101 31 76C34 48 62 33 90 27Z",
  complete:
    "M90 24C118 24 145 36 150 63C155 91 134 116 112 125C87 137 63 128 47 113C29 95 25 69 40 47C53 28 66 24 90 24Z",
  error:
    "M90 30C113 7 131 35 147 54C167 77 135 93 139 117C142 142 105 128 83 132C55 139 18 117 28 89C37 65 60 40 90 30Z",
};
function AgentStateImpl({
  status = "idle",
  size = "md",
  label,
  description,
  className,
  ...props
}: AgentStateProps) {
  const id = React.useId().replace(/:/g, "");
  const ref = React.useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "40px" });
  const { quiet, transition } = useChoreography();
  const [visible, setVisible] = React.useState(true);
  React.useEffect(() => {
    const update = () => setVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const active =
    !quiet &&
    inView &&
    visible &&
    (status === "thinking" || status === "working");
  const contour = silhouettes[status];
  const alternate = silhouettes[status === "thinking" ? "working" : "thinking"];
  const pathAnimation = active
    ? { d: [contour, alternate, contour] }
    : { d: contour };
  const fieldTransition = active
    ? {
        duration: status === "working" ? 5 : 7,
        repeat: Infinity,
        ease: "easeInOut" as const,
      }
    : transition;
  return (
    <div
      ref={ref}
      data-slot="agent-state"
      data-status={status}
      data-size={size}
      data-animated={active || undefined}
      className={cn("v-agent-state", className)}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      {...props}
    >
      <svg
        className="v-agent-state__field"
        viewBox="0 0 180 160"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <radialGradient id={`${id}-body`} cx=".3" cy=".2" r=".85">
            <stop stopColor="var(--agent-light)" />
            <stop offset=".5" stopColor="var(--agent-base)" />
            <stop offset="1" stopColor="var(--agent-deep)" />
          </radialGradient>
          <radialGradient id={`${id}-fold`} cx=".65" cy=".22" r=".8">
            <stop stopColor="var(--cream-fixed)" stopOpacity=".84" />
            <stop offset=".4" stopColor="var(--agent-light)" stopOpacity=".7" />
            <stop offset="1" stopColor="var(--agent-deep)" stopOpacity=".2" />
          </radialGradient>
          <linearGradient
            id={`${id}-rim`}
            x1="30"
            y1="30"
            x2="138"
            y2="134"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="var(--cream-fixed)" stopOpacity=".92" />
            <stop
              offset=".48"
              stopColor="var(--agent-light)"
              stopOpacity=".2"
            />
            <stop offset="1" stopColor="var(--agent-deep)" stopOpacity=".8" />
          </linearGradient>
          <clipPath id={`${id}-clip`}>
            <motion.path
              initial={false}
              d={contour}
              animate={pathAnimation}
              transition={fieldTransition}
            />
          </clipPath>
        </defs>
        <ellipse
          cx="92"
          cy="139"
          rx="43"
          ry="5"
          fill="var(--agent-deep)"
          opacity=".12"
        />
        <motion.path
          initial={false}
          d={contour}
          animate={pathAnimation}
          transition={fieldTransition}
          fill={`url(#${id}-body)`}
        />
        <g clipPath={`url(#${id}-clip)`}>
          <motion.g
            initial={false}
            animate={
              active
                ? { rotate: [0, 12, -6, 0], x: [0, 5, -3, 0] }
                : { rotate: 0, x: 0 }
            }
            transition={
              active
                ? { duration: 10, repeat: Infinity, ease: "easeInOut" }
                : transition
            }
            style={{ transformOrigin: "90px 80px" }}
          >
            <path
              d="M15 61C51 32 81 110 128 89C165 72 142 24 105 14C163 7 181 113 125 142C74 168 20 125 15 61Z"
              fill={`url(#${id}-fold)`}
            />
            <path
              d="M26 48C64 18 59 134 119 110C147 99 132 71 155 47"
              stroke={`url(#${id}-rim)`}
              strokeWidth="1.2"
            />
            <path
              d="M30 44C69 19 58 139 125 111C151 99 136 69 159 43"
              stroke={`url(#${id}-rim)`}
              strokeWidth=".65"
              opacity=".75"
            />
            <path
              d="M35 42C74 26 64 143 131 109C154 97 141 65 162 40"
              stroke={`url(#${id}-rim)`}
              strokeWidth=".5"
              opacity=".5"
            />
            <path
              d="M24 92C47 78 93 148 139 118"
              stroke="var(--agent-deep)"
              strokeOpacity=".25"
              strokeWidth="14"
            />
          </motion.g>
        </g>
        <motion.path
          initial={false}
          d={contour}
          animate={pathAnimation}
          transition={fieldTransition}
          stroke={`url(#${id}-rim)`}
          strokeWidth="1.2"
        />
        <g
          className="v-agent-state__mark"
          stroke="var(--ink-fixed)"
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {status === "complete" ? (
            <path d="m77 79 9 9 19-21" />
          ) : status === "error" ? (
            <>
              <path d="M90 66v16" />
              <path d="M90 91h.01" />
            </>
          ) : status === "needs-input" ? (
            <>
              <path d="M84 72a7 7 0 0 1 14 0c0 5-8 6-8 11" />
              <path d="M90 92h.01" />
            </>
          ) : (
            <>
              <path d="M77 77v5M101 77v5" />
              <path d={status === "idle" ? "M84 91q6 4 12 0" : "M85 91h10"} />
            </>
          )}
        </g>
      </svg>
      <div className="v-agent-state__copy">
        <span className="v-agent-state__label">
          {label ?? stateLabels[status]}
        </span>
        {description && (
          <span className="v-agent-state__description">{description}</span>
        )}
      </div>
    </div>
  );
}
export function AgentState(props: Parameters<typeof AgentStateImpl>[0]) {
  return (
    <>
      <CojeevStyles />
      <AgentStateImpl {...props} />
    </>
  );
}

// ---- Styles (React 19 hoists this <style> into <head> and renders it once per page) ----
const COJEEV_CSS = `/* Agent state — styles for 000h by Cojeev (MIT). Plain CSS with native cascade layers; no Tailwind theme or config needed.
   Dark mode: put the dark class on <html> or an ancestor (shadcn convention); [data-mode="dark"] works too.
   Fonts: uses the host application system type; no external font download. */
@layer theme, base, components, utilities, cojeev-states, cojeev-flow, cojeev-morph, cojeev-accessibility;

/* ---- Tokens: :root is light; [data-mode="dark"] and the shadcn .dark class are dark ---- */
/* Cojeev tokens: one definition per mode. The runtime palettes in lib/appearance-tokens.ts ("paper" is
   this default) re-point these at runtime. Contrast notes below are measured against these values. */
[data-slot="agent-state"]{
color-scheme:light;
/* accents [E] I03 */
--v-pink:#F0A4CC;--v-olive:#A8BC75;--v-blue:#95BAE8;--v-yellow:#F1D369;
/* surfaces [M] */
--v-canvas:#F8F6F1;--v-paper:#FFFFFF;/* @kind color */--v-beige:#EEE9E1;--v-beige-2:#f3efe8;--v-cream-pill:#FFFFFF;
--v-ink:#26282d;--v-structure:#14171B;--on-structure:#F9FAFC;--structure-quiet:#242931;--structure-line:#565D68;--structure-text:#E2E6ED;--v-ink-soft:#464951;--v-on-ink:#F8F6F1;
/* text [M] */
--v-text:#26282d;--v-text-2:#464951;--v-text-3:#52565e;--v-skel-face:#EEE9E1;--v-skel-sheen:#FFFFFF;--v-skel-edge:#b4b0ab;--v-disabled-ink:#52565e;--v-disabled-face:#EEE9E1;--v-disabled-edge:#706e6d;/* text-3 6.8:1 on canvas, 6.1:1 on beige — informational grey clears AA on both real surfaces */
/* semantic hues */
--v-danger:#D7473C;/* [M] I07 I16 — FILL only: dots, borders, destructive button (white on it passes) */
--v-danger-ink:#b2433b;--v-danger-fill:#B92D28;/* white text on it = 6.1:1 */--v-olive-ink:#525d3d;/* 6.5:1 on canvas */--v-accent-ink:#704f63;/* weekend / accent ink, 5.8:1 on beige *//* danger ink is text-only: 4.7:1 on --v-danger-soft, 4.6:1 on --v-beige */
--v-brand:#845c73;/* Cojeev mulberry — focus ring only (decision); 5.2:1 on canvas */
--v-border:#b4b0ab;/* hairlines between static surfaces only — 1.8:1 on beige, 2.0:1 on canvas; never a control edge */
--v-edge:#706e6d;/* control edge: 4.2:1 on beige, 4.7:1 on canvas — above the 3:1 floor for interactive boundaries */
--switch-knob:#FFFFFF;--switch-knob-on:#14171B;
/* ---- semantic roles: surfaces, selection, status, data ----
   Deliberate tinted regions so a page is not uniformly beige. Each is a light wash of an identity hue,
   keeping ink text at ≥ 4.5:1 (measured: quiet 14.8, work 13.6, automation 14.0, memory 13.5,
   library 13.6, ai 13.6, alert 13.2). */
--surface-quiet:#FFFFFF;--surface-work:#f1f6fc;--surface-automation:#fdf9ec;--surface-memory:#f4f6ed;
--surface-library:#fdf3f8;--surface-ai:#f1f6fc;--surface-alert:#fcf0ee;
--sel-bg:#fbe9f3;--sel-edge:#a87491;--sel-ink:#26282d;
--status-ok-bg:#f4f6ed;--status-ok-ink:#555f3f;--status-warn-bg:#fdf9ec;--status-warn-ink:#695d33;
--status-danger-bg:#fae7e6;--status-danger-ink:#96342d;--status-info-bg:#f1f6fc;--status-info-ink:#4b5d74;
--status-pending-bg:#e7e7e8;--status-pending-ink:#464951;
--v-scrim:rgba(19,24,32,.46);/* [I] I07 gave a beige veil; a cream dialog on a beige veil measured 1.04:1 and vanished. A warm-ink veil keeps the paper feel and lets the modal stand off the page. */
--v-disabled-fill:#EEE9E1;/* [M] I18 grey Join pill */
/* tonal watermarks [M] ≈ accent 88% + black */
--v-pink-deep:#d693b7;--v-olive-deep:#96a86a;--v-blue-deep:#86a6cf;--v-yellow-deep:#d6bc60;/* [M] I15 watermarks + hover: the SAME hue ~8–12 % darker, not a heavy mix */
/* soft tints for tag pills on beige [I] */
--v-pink-soft:#fbe9f3;
--v-olive-soft:#eaefde;
--v-blue-soft:#e6eef9;
--v-yellow-soft:#fcf4db;
--v-danger-soft:#fae7e6;
/* semantic roles (shadcn-style names) */--card-2:var(--v-beige-2);
/* categories (decision) */
--cat-work:var(--v-blue);--cat-automations:var(--v-yellow);--cat-memory:var(--v-olive);--cat-library:var(--v-pink);--cat-ai-apps:var(--v-blue);--cat-free-models:var(--v-olive);--cat-settings:var(--v-beige);--cat-needs-you:var(--v-pink);--cat-runs:var(--v-yellow);
/* status words — always paired with text/icon */
--status-ok:var(--v-olive);--status-warn:var(--v-yellow);--status-danger:var(--v-danger);--status-info:var(--v-blue);--status-pending:var(--v-ink-soft);--status-off:var(--v-text-3);
/* type */
--font-display:inherit;
--font-text:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
--v-font-mono:ui-monospace,"SF Mono",Menlo,monospace;/* terminal only */
/* type scale — every font-size in the library is one of these steps; nothing sits between them.
   hero and display are headlines, section and title head blocks, lead opens a passage, reading is long-form
   copy, body is interface copy, control labels controls, small is helper text under a label, meta is
   secondary data, caps is the smallest step and the floor for any text. */
--fs-hero:72px;--fs-display:44px;--fs-section:26px;--fs-title:21px;--fs-lead:17px;--fs-reading:16px;--fs-body:15px;--fs-control:14px;--fs-small:13px;--fs-meta:12px;--fs-caps:11px;
--lh-hero:.95;/* @kind other */
--lh-display:1.05;/* @kind other */
--lh-title:1.2;/* @kind other */
--lh-body:1.45;/* @kind other */
--lh-control:1.2;/* @kind other */
/* weights — four steps only; the variable faces can do more, the system does not */
--fw-regular:400;/* @kind other */
--fw-medium:500;/* @kind other */
--fw-semibold:600;/* @kind other */
--fw-bold:700;/* @kind other */
--fw-display:var(--fw-medium);/* @kind other */
--fw-title:var(--fw-semibold);/* @kind other */
--fw-body:var(--fw-regular);/* @kind other */
--fw-control:var(--fw-medium);/* @kind other */
--fw-value:var(--fw-bold);/* @kind other */
--ls-display:-.015em;/* @kind other */
--ls-hero:-.03em;/* @kind other */
--ls-caps:.06em;/* @kind other */
/* space — the 4px grid. Padding, margin and gap use these steps; only 1-3px optical nudges stay raw. */
--s-1:4px;--s-2:8px;--s-3:12px;--s-4:16px;--s-5:20px;--s-6:24px;--s-7:28px;--s-8:32px;--s-10:40px;--s-12:48px;--s-16:64px;
/* layout [M] I15 → 1440 */
--shell-inset:28px;--sidebar-w:212px;--sidebar-w-mini:76px;--sidebar-gap:52px;--rail-w:360px;--rail-gap:40px;--topbar-h:44px;--content-max:1440px;
--card-pad:24px;--card-gap:16px;--row-pad:12px 16px;--item-h:64px;--content-offset:16px;--agenda-slot:80px;
/* radius — every corner is one of these steps */
--r-xs:4px;--r-sm:8px;--r-md:12px;--r-card-sm:16px;--r-card:20px;--r-panel:24px;--r-sheet:28px;--r-frame:40px;--r-pill:999px;
/* dimensions [M/O] */
--disk-sm:32px;
--disk-md:40px;
--disk-lg:48px;
--icon-sm:16px;
--icon-md:20px;
--icon-lg:24px;
--icon-stroke:1.6;/* @kind other */
--ctl-sm:32px;
--ctl-md:40px;
--ctl-lg:48px;
--ctl-xl:56px;
--utility:44px;
--utility-overlap:-4px;/* @kind other */
--dock-h:72px;--dock-action:56px;--dock-shoulder:24px;--assist-close:48px;--hex:24px;--edit-badge:36px;
--track-h:10px;--track-h-lg:14px;--track-h-sm:6px;--table-row:72px;--table-head:44px;--nav-row:40px;--date-col:44px;
--hit-min:44px;
/* borders [I] */
--bw-hair:1px;
--bw-featured:1.5px;
--bw-dash:1px dashed var(--v-text-2);/* @kind other */
/* elevation — app surfaces are flat; only floating layers get a shadow [I] */
--shadow-none:none;--shadow-float:0 12px 32px -12px rgba(17,17,17,.18);--shadow-lift:0 1px 0 rgba(17,17,17,.06);
/* z [I] */
--z-base:0;/* @kind other */
--z-sticky:10;/* @kind other */
--z-dock:20;/* @kind other */
--z-sheet:30;/* @kind other */
--z-assist:35;/* @kind other */
--z-dialog:40;/* @kind other */
--z-popover:45;/* @kind other */
--z-toast:50;/* @kind other */
--z-tooltip:60;/* @kind other */
/* motion [I] — decision: alive but unobtrusive */
--t-micro:120ms;/* @kind other */
--t-element:200ms;/* @kind other */
--t-max:300ms;/* @kind other */
--t-draw:600ms;/* @kind other */
--t-count:700ms;/* @kind other */
--breath:6s;/* @kind other */
--enter:cubic-bezier(.2,.8,.2,1);/* @kind other */
--exit:cubic-bezier(.4,0,1,1);/* @kind other */
/* ---- component parameters ----
   Per-instance knobs that components re-point on their own selectors (a hue for an accordion row, the fill a
   motion body paints, a skeleton's face). Registered here with their defaults so every declaration below is a
   known parameter, not an unregistered token. */
--pulse:34px;/* @kind spacing */
--pulse-c:var(--v-pink);/* @kind color */
--c:var(--v-beige);/* @kind color */
--hue:var(--v-pink);/* @kind color */
--hue-deep:var(--v-pink-deep);/* @kind color */
--hue-ink:var(--v-text);/* @kind color */
--wm-m:none;/* @kind other */
--wm:var(--v-beige-2);/* @kind color */
--skel:var(--v-skel-face);/* @kind color */
--sw:var(--v-pink);/* @kind color */
--dot:var(--v-border);/* @kind color */
--disk-bg:var(--v-beige);/* @kind color */
--mfill:transparent;/* @kind color */
--mstroke:transparent;/* @kind color */
--glide-bg:#14171B;/* @kind color */ /* the travelling lozenge is dark in BOTH themes so its cream label always reads */
--glide-fg:#F9FAFC;/* @kind color */
--v-on-accent:#14171B;/* @kind color */ /* ink on pink / yellow / olive / blue, both modes */
/* ---- fixed inks [I] — values that the component sheets painted as raw hex and that do NOT follow the mode switch (the visual is unchanged by tokenising them) ---- */
--ink-fixed:#111111;/* @kind color */ /* structure fills / borders that stay ink in dark mode */
--cream-fixed:#F6EFE2;/* @kind color */ /* cream label on the ink rail, both modes */
--mask-ink:#000000;/* @kind color */ /* opaque paint inside mask-image gradients — only its alpha matters */
--unavail-ink:#52565e;/* @kind color */ /* "unavailable" and disabled date-strip ink */
--alert-ink:#464951;/* @kind color */ /* alert body text and kicker */
--btn-disabled-ink:#52565e;/* @kind color */ /* disabled button label */
--nav-group-ink:#52565e;/* @kind color */ /* catalog rail group label */
--muted-foreground-ink:#2E2A24;/* @kind color */ /* muted text on ink-adjacent surfaces (notch, feature media, selected item) */
--muted-foreground-tinted:#4A443C;/* @kind color */ /* muted text on soft tints and cream cards */
/* ---- legacy kit values [I] — referenced only by legacy-aliases.css for consumers still on the retired names ---- */
--danger-deep:#E9A79F;/* @kind color */ /* the danger alert's deep tint */
--legacy-on-brand:#FDF6F9;/* @kind color */--legacy-accent-5:#E29A6A;/* @kind color */--legacy-success:#5C8C34;/* @kind color */--legacy-warning:#B9831C;/* @kind color */--legacy-info:#3F79B4;/* @kind color */--legacy-danger-fill:#A8402A;/* @kind color */--legacy-success-fill:#3F6B22;/* @kind color */
--rail-sel:rgba(251,244,230,.1);/* @kind color */
--rail-hover:rgba(251,244,230,.055);/* @kind color */
/* ---- the travelling selection: per-character timing [I] — the per-character timing IS the feature; js/flow.js reads these too ---- */
--t-flow-glide:.24s;/* @kind other */--t-flow-glide-h:.24s;/* @kind other */--t-flow-glide-land:.36s;/* @kind other */
--t-flow-stretch:.3s;/* @kind other */--t-flow-stretch-p1:.16s;/* @kind other */
--t-flow-jelly:.5s;/* @kind other */--t-flow-jelly-h:.44s;/* @kind other */--t-flow-jelly-hover:.3s;/* @kind other */--t-flow-jelly-land:.52s;/* @kind other */
--t-flow-comet:.34s;/* @kind other */--t-flow-comet-h:.3s;/* @kind other */--t-flow-comet-trail:.72s;/* @kind other */--t-flow-comet-trail-h:.6s;/* @kind other */
--t-flow-drop:.3s;/* @kind other */--t-flow-drop-gather:.14s;/* @kind other */--t-flow-drop-shoot:.18s;/* @kind other */--t-flow-drop-land:.3s;/* @kind other */
--t-flow-rubber:.36s;/* @kind other */--t-flow-rubber-lead:.2s;/* @kind other */
--t-flow-pebble:.46s;/* @kind other */--t-flow-pebble-h:.4s;/* @kind other */--t-flow-pebble-land:.5s;/* @kind other */
--t-flow-ripple:.36s;/* @kind other */--t-flow-ripple-h:.3s;/* @kind other */--t-flow-ripple-ring:.6s;/* @kind other */--t-flow-ripple-delay:.18s;/* @kind other */
--t-flow-halo:.4s;/* @kind other */--t-flow-halo-h:.34s;/* @kind other */--t-flow-halo-glow:.7s;/* @kind other */
--t-flow-hover:.22s;/* @kind other */--t-flow-radius:.3s;/* @kind other */--t-flow-radius-sm:.2s;/* @kind other */--t-flow-fade:.18s;/* @kind other */--t-flow-fade-sm:.16s;/* @kind other */
--t-flow-label:.2s;/* @kind other */--t-flow-label-delay:.1s;/* @kind other */--t-flow-still:60ms;/* @kind other */--t-flow-land-hold:900ms;/* @kind other */
--t-skel:1.4s;/* @kind other */--t-skel-sheen:2.4s;/* @kind other */--t-pulse:2.1s;/* @kind other */
--e-flow-glide:cubic-bezier(.2,.8,.2,1);/* @kind other */--e-flow-stretch:cubic-bezier(.3,1.15,.4,1);/* @kind other */--e-flow-stretch-p1:cubic-bezier(.4,0,.2,1);/* @kind other */
--e-flow-jelly:cubic-bezier(.3,1.3,.45,1);/* @kind other */--e-flow-jelly-hover:cubic-bezier(.3,1.25,.45,1);/* @kind other */--e-flow-comet:cubic-bezier(.2,.8,.2,1);/* @kind other */--e-flow-comet-trail:cubic-bezier(.2,.7,.15,1);/* @kind other */
--e-flow-drop:cubic-bezier(.3,1.25,.4,1);/* @kind other */--e-flow-drop-gather:cubic-bezier(.4,0,.6,1);/* @kind other */--e-flow-drop-shoot:cubic-bezier(.3,0,.2,1);/* @kind other */
--e-flow-rubber:cubic-bezier(.3,1.3,.4,1);/* @kind other */--e-flow-rubber-lead:cubic-bezier(.2,.9,.3,1);/* @kind other */--e-flow-pebble:cubic-bezier(.32,1.25,.42,1);/* @kind other */
--e-flow-ripple:cubic-bezier(.2,.8,.2,1);/* @kind other */--e-flow-halo:cubic-bezier(.3,1.2,.4,1);/* @kind other */--e-flow-settle:cubic-bezier(.2,.7,.2,1);/* @kind other */
/* ---- ui.js timings [I] ---- */
--t-tooltip:220ms;/* @kind other */--t-hovercard:300ms;/* @kind other */--t-toast:5000ms;/* @kind other */--t-focus-settle:120ms;/* @kind other */
}
/* dark */
:root[data-mode="dark"] [data-slot="agent-state"], .dark [data-slot="agent-state"]{
color-scheme:dark;
/* surfaces */
--v-canvas:#15171A;--v-paper:#20242A;--v-beige:#292F37;--v-beige-2:#20242a;--v-cream-pill:#20242A;
/* ink and text */
--v-ink:#f3f4f4;--v-ink-soft:#bdc1c5;--v-on-ink:#15171A;--v-on-accent:#14171B;--v-text:#f3f4f4;--v-text-2:#bdc1c5;--v-text-3:#a9aeb4;--alert-ink:#bdc1c5;--nav-group-ink:#a9aeb4;--unavail-ink:#a9aeb4;--btn-disabled-ink:#a9aeb4;
/* edges */
--v-border:#4e5359;--v-edge:#8c9094;--v-brand:#F0A4CC;--v-scrim:rgba(0,0,0,.66);
/* accents */
--v-pink:#F0A4CC;--v-pink-deep:#d693b7;--v-pink-soft:#3f3742;--v-olive:#A8BC75;--v-olive-deep:#96a86a;--v-olive-soft:#343b35;--v-olive-ink:#A8BC75;--v-blue:#95BAE8;--v-blue-deep:#86a6cf;--v-blue-soft:#323b47;--v-yellow:#F1D369;--v-yellow-deep:#d6bc60;--v-yellow-soft:#3f3e33;--v-accent-ink:#F0A4CC;
/* danger */
--v-danger:#D7473C;--v-danger-fill:#B92D28;--v-danger-ink:#e3786f;--v-danger-soft:#36282c;
/* structure */
--v-structure:#14171B;--on-structure:#F9FAFC;--structure-quiet:#242931;--structure-line:#565D68;--structure-text:#E2E6ED;--glide-bg:#14171B;--glide-fg:#F9FAFC;
/* states */
--v-skel-face:#292F37;--v-skel-sheen:#20242A;--v-skel-edge:#4e5359;--v-disabled-ink:#a9aeb4;--v-disabled-face:#292F37;--v-disabled-edge:#8c9094;--v-disabled-fill:#292F37;--switch-knob:#20242A;--switch-knob-on:#14171B;--sel-bg:#433a46;--sel-edge:#F0A4CC;--sel-ink:#f3f4f4;
/* semantic surfaces: identity hues over the dark canvas, so a tinted region keeps its meaning and its text contrast */
--surface-quiet:#20242A;--surface-work:#2e3641;--surface-automation:#393932;--surface-memory:#303633;--surface-library:#39333d;--surface-ai:#2e3641;--surface-alert:#383034;
/* status */
--status-ok-bg:#303633;--status-ok-ink:#adc07c;--status-warn-bg:#393932;--status-warn-ink:#F1D369;--status-danger-bg:#36282c;--status-danger-ink:#e99891;--status-info-bg:#2e3641;--status-info-ink:#97bce9;--status-pending-bg:#33373d;--status-pending-ink:#bdc1c5;
/* elevation */
--shadow-float:0 12px 32px -12px rgba(0,0,0,.6);
}
@media (prefers-reduced-motion:reduce){[data-slot="agent-state"]{
--t-micro:0ms;/* @kind other */
--t-element:0ms;/* @kind other */
--t-max:0ms;/* @kind other */
--t-draw:0ms;/* @kind other */
--t-count:0ms;/* @kind other */
}}

/* ---- Reset and shared rules (scoped to [data-slot] so the host page is untouched) ---- */
/* Reset follows the reference. Component rules live in layers so accessibility
   overrides can come last without an importance flag. */
@layer base {
  :where([data-slot]) *,
  :where([data-slot]),
  :where([data-slot]) *::before,
  :where([data-slot])::before,
  :where([data-slot]) *::after,
  :where([data-slot])::after { box-sizing:border-box; border-width:0; border-style:none; }
  :where([data-slot]:not([data-slot] [data-slot], [data-slot="shape"], [data-slot="shape-morph"], [data-slot="icon"], [data-slot="animated-icon"], [data-slot="state-chevron"])) { color:var(--v-text); font-family:var(--font-text); font-size:var(--fs-body); line-height:var(--lh-body); font-weight:var(--fw-body); -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
  :where([data-slot]) h1,
  h1:where([data-slot]),
  :where([data-slot]) h2,
  h2:where([data-slot]),
  :where([data-slot]) h3,
  h3:where([data-slot]),
  :where([data-slot]) h4,
  h4:where([data-slot]),
  :where([data-slot]) p,
  p:where([data-slot]),
  :where([data-slot]) figure,
  figure:where([data-slot]),
  :where([data-slot]) ul,
  ul:where([data-slot]),
  :where([data-slot]) ol,
  ol:where([data-slot]) { margin:0; }
  /* Headings balance their lines so a short last word never sits alone; long copy avoids orphans. */
  :where([data-slot]) h1,
  h1:where([data-slot]),
  :where([data-slot]) h2,
  h2:where([data-slot]),
  :where([data-slot]) h3,
  h3:where([data-slot]),
  :where([data-slot]) h4,
  h4:where([data-slot]) { text-wrap:balance; }
  :where([data-slot]) p,
  p:where([data-slot]) { text-wrap:pretty; }
  :where([data-slot]) button,
  button:where([data-slot]),
  :where([data-slot]) input,
  input:where([data-slot]),
  :where([data-slot]) select,
  select:where([data-slot]),
  :where([data-slot]) textarea,
  textarea:where([data-slot]) { font:inherit; color:inherit; }
  :where([data-slot]) code,
  code:where([data-slot]),
  :where([data-slot]) pre,
  pre:where([data-slot]),
  :where([data-slot]) samp,
  samp:where([data-slot]) { font-family:monospace; }
  :where([data-slot]) button,
  button:where([data-slot]) { background:none; border:0; padding:0; cursor:pointer; }
  :where([data-slot]) :where(a[href],area[href],summary,label[for],label:has(input),select,input:is([type="checkbox"],[type="radio"],[type="range"],[type="button"],[type="submit"],[type="reset"],[type="file"]),[role="button"],[role="checkbox"],[role="radio"],[role="switch"],[role="tab"],[role="option"],[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"]),
  :where(a[href],area[href],summary,label[for],label:has(input),select,input:is([type="checkbox"],[type="radio"],[type="range"],[type="button"],[type="submit"],[type="reset"],[type="file"]),[role="button"],[role="checkbox"],[role="radio"],[role="switch"],[role="tab"],[role="option"],[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"]):where([data-slot]) { cursor:pointer; }
  /* Hit-test the control, not changing decorative SVG paths. Icon feedback
     already listens to the owning control. Standalone interactive art is intact. */
  :where(button,a[href],summary,[role="button"],[role="tab"],[role^="menuitem"],[role="option"],[role="checkbox"],[role="radio"],[role="switch"])
    :where([data-slot="icon"][aria-hidden="true"],[data-slot="animated-icon"]:has([data-slot="icon"][aria-hidden="true"]),[data-slot="shape"][aria-hidden="true"],[data-slot="state-chevron"][aria-hidden="true"]) { pointer-events:none; }
  /* Preserve the original browser touch feedback on library elements. */
  :where([data-slot]) { -webkit-tap-highlight-color:initial; }
  :where([data-slot]) img,
  img:where([data-slot]),
  :where([data-slot]) svg,
  svg:where([data-slot]) { display:block; max-width:100%; }
  :where([data-slot]) a,
  a:where([data-slot]) { color:var(--v-text); text-underline-offset:2px; }
  /* The reference preserves native link decoration; Tailwind preflight resets it. */
  :where([data-slot]) a:any-link,
  a:any-link:where([data-slot]) { text-decoration-line:underline; }
  :where([data-slot]) a:hover,
  a:hover:where([data-slot]) { color:var(--v-text-2); }
  :where([data-slot]) :focus-visible,
  :focus-visible:where([data-slot]) { outline:2px solid var(--v-brand); outline-offset:2px; border-radius:var(--r-sm); }
  :where([data-slot]) *::selection,
  :where([data-slot])::selection { background:var(--v-pink); color:var(--ink-fixed); }
}
/* Disabled controls remain hit-testable so their unavailable cursor is visible.
   Their native primitive or event guard still owns activation prevention. */
:where([data-slot]) :is(button,input,select,textarea,[role],[data-slot]):is(:disabled,[aria-disabled="true"],[data-disabled]:not([data-disabled="false"])),
  :is(button,input,select,textarea,[role],[data-slot]):is(:disabled,[aria-disabled="true"],[data-disabled]:not([data-disabled="false"])):where([data-slot]),
  :where([data-slot]) label:has(input:disabled),
  label:has(input:disabled):where([data-slot]) { cursor:not-allowed; }
:where([data-slot]) :is([aria-disabled="true"],[data-disabled]:not([data-disabled="false"]),label:has(input:disabled)) :where(span,svg,path),
  :is([aria-disabled="true"],[data-disabled]:not([data-disabled="false"]),label:has(input:disabled)) :where(span,svg,path):where([data-slot]) { cursor:inherit; }
@layer components {
  :where([data-slot]) .v-body-2,
  .v-body-2:where([data-slot]) { font-size:var(--fs-body); line-height:1.5; color:var(--v-text-2); }
  :where([data-slot]) .v-meta,
  .v-meta:where([data-slot]) { font-size:var(--fs-meta); line-height:1.3; color:var(--v-text-2); }
  :where([data-slot]) .v-id,
  .v-id:where([data-slot]) { font-variant-numeric:tabular-nums; letter-spacing:.02em; }
  :where([data-slot]) .v-icon,
  .v-icon:where([data-slot]) { width:var(--icon-md); height:var(--icon-md); flex:none; stroke-width:var(--icon-stroke); fill:none; }
}
@layer cojeev-accessibility {
  :where([data-slot]) [hidden]:not([hidden="until-found"]),
  [hidden]:not([hidden="until-found"]):where([data-slot]) { display:none; }
  :where([data-slot]) .v-sr,
  .v-sr:where([data-slot]) { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); clip-path:inset(50%); white-space:nowrap; border:0; inset-inline-start:0; inset-block-start:0; }
  @media (prefers-reduced-motion:reduce) {
    :where([data-slot]) *,
  :where([data-slot]),
  :where([data-slot]) *::before,
  :where([data-slot])::before,
  :where([data-slot]) *::after,
  :where([data-slot])::after { animation-duration:0s; animation-iteration-count:1; transition-duration:0s; scroll-behavior:auto; }
  }
}

/* ---- agent-state styles ---- */
@layer cojeev-states {
[data-slot="agent-state"] {
  --agent-base: var(--v-pink);
  --agent-light: var(--v-yellow);
  --agent-deep: var(--v-pink-deep);
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--s-3);
  color: var(--v-text);
}
[data-slot="agent-state"][data-status="thinking"] { --agent-base: var(--v-blue); --agent-light: var(--v-pink); --agent-deep: var(--v-blue-deep); }
[data-slot="agent-state"][data-status="working"] { --agent-base: var(--v-pink); --agent-light: var(--v-yellow); --agent-deep: var(--v-pink-deep); }
[data-slot="agent-state"][data-status="needs-input"] { --agent-base: var(--v-yellow); --agent-light: var(--cream-fixed); --agent-deep: var(--v-yellow-deep); }
[data-slot="agent-state"][data-status="complete"] { --agent-base: var(--v-olive); --agent-light: var(--v-yellow); --agent-deep: var(--v-olive-deep); }
[data-slot="agent-state"][data-status="error"] { --agent-base: var(--v-pink); --agent-light: var(--v-yellow); --agent-deep: var(--v-danger); }
.v-agent-state__field { display: block; width: 88px; height: auto; flex: 0 0 auto; overflow: visible; pointer-events: none; }
.v-agent-state__copy { display: grid; min-width: 0; gap: var(--s-1); }
.v-agent-state__label { font: var(--fw-semibold) var(--fs-lead)/1.25 var(--font-display); letter-spacing: -.02em; overflow-wrap: anywhere; }
.v-agent-state__description { font: var(--fw-regular) var(--fs-small)/1.45 var(--font-text); color: var(--v-text-2); max-width: 35ch; overflow-wrap: anywhere; }
[data-slot="agent-state"][data-size="sm"] { gap: var(--s-1); }
[data-slot="agent-state"][data-size="sm"] .v-agent-state__field { width: 48px; }
[data-slot="agent-state"][data-size="sm"] .v-agent-state__label { font-family: var(--font-text); font-size: var(--fs-small); letter-spacing: 0; }
[data-slot="agent-state"][data-size="sm"] .v-agent-state__description { font-size: var(--fs-meta); }
[data-slot="agent-state"][data-size="lg"] { flex-direction: column; text-align: center; gap: 0; }
[data-slot="agent-state"][data-size="lg"] .v-agent-state__field { width: min(100%, 216px); }
[data-slot="agent-state"][data-size="lg"] .v-agent-state__label { font-size: var(--fs-section); }
[data-slot="agent-state"][data-size="lg"] .v-agent-state__description { max-width: 32ch; margin-inline: auto; font-size: var(--fs-control); }
@media (forced-colors: active) {
  .v-agent-state__field { forced-color-adjust: none; }
}
}
`;

function CojeevStyles() {
  return (
    <style href="000h-agent-state" precedence="default">
      {COJEEV_CSS}
    </style>
  );
}
