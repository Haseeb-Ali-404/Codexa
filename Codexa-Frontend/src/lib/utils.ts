import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Used by chat + code viewers: user is “following” new output when this near the bottom */
export const STICKY_BOTTOM_THRESHOLD_PX = 100;

export function isElementNearBottom(
  el: HTMLElement,
  thresholdPx: number = STICKY_BOTTOM_THRESHOLD_PX,
) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= thresholdPx;
}
