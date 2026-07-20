import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent, WheelEvent } from "react";

const MIN_ZOOM = 1;
const MAX_ZOOM = 6;
const WHEEL_STEP = 1.12;
const IDENTITY_EPSILON = 1.001;

export function clampZoom(zoom: number, factor: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * factor));
}

export function isIdentityZoom(zoom: number): boolean {
  return zoom <= IDENTITY_EPSILON;
}

interface ZoomState {
  zoom: number;
  panX: number;
  panY: number;
}

const IDENTITY: ZoomState = { zoom: 1, panX: 0, panY: 0 };

export interface UseFrameZoom {
  zoom: number;
  panX: number;
  panY: number;
  isZoomed: boolean;
  isDragging: boolean;
  transformCss: string;
  reset: () => void;
  handlers: {
    onWheel: (e: WheelEvent) => void;
    onPointerDown: (e: PointerEvent) => void;
    onPointerMove: (e: PointerEvent) => void;
    onPointerUp: (e: PointerEvent) => void;
  };
}

/**
 * Spatial (in-frame) zoom/pan for a video preview — port of VideoEditor.qml's
 * picZoom/picPanX/picPanY (deleted in the F3 QML removal, commit d64f38a).
 * Scroll to zoom (x1.12 per tick, clamped 1x-6x), drag to pan in unscaled
 * screen pixels once zoomed in. Pass a resetKey (e.g. the clip's source path)
 * to snap back to identity whenever it changes.
 */
export function useFrameZoom(resetKey?: string | number | null): UseFrameZoom {
  const [state, setState] = useState<ZoomState>(IDENTITY);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef({ startX: 0, startY: 0, baseX: 0, baseY: 0 });

  const reset = useCallback(() => {
    setState(IDENTITY);
    setIsDragging(false);
  }, []);

  useEffect(() => {
    reset();
  }, [resetKey, reset]);

  const nudge = useCallback((factor: number) => {
    setState((prev) => {
      const zoom = clampZoom(prev.zoom, factor);
      return isIdentityZoom(zoom) ? IDENTITY : { ...prev, zoom };
    });
  }, []);

  const onWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      if (e.deltaY === 0) return;
      nudge(e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP);
    },
    [nudge]
  );

  const onPointerDown = useCallback(
    (e: PointerEvent) => {
      if (isIdentityZoom(state.zoom)) return;
      e.preventDefault();
      (e.target as Element).setPointerCapture(e.pointerId);
      dragRef.current = { startX: e.clientX, startY: e.clientY, baseX: state.panX, baseY: state.panY };
      setIsDragging(true);
    },
    [state.zoom, state.panX, state.panY]
  );

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!isDragging) return;
      const { startX, startY, baseX, baseY } = dragRef.current;
      setState((prev) => ({ ...prev, panX: baseX + (e.clientX - startX), panY: baseY + (e.clientY - startY) }));
    },
    [isDragging]
  );

  const onPointerUp = useCallback(
    (e: PointerEvent) => {
      if (!isDragging) return;
      (e.target as Element).releasePointerCapture(e.pointerId);
      setIsDragging(false);
    },
    [isDragging]
  );

  return {
    zoom: state.zoom,
    panX: state.panX,
    panY: state.panY,
    isZoomed: !isIdentityZoom(state.zoom),
    isDragging,
    transformCss: `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`,
    reset,
    handlers: { onWheel, onPointerDown, onPointerMove, onPointerUp },
  };
}
