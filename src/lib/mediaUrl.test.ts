import { describe, expect, it } from "vitest";
import { clipUrl, previewUrl } from "./mediaUrl";

function decodeUrlSafeBase64NoPad(s: string): string {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(s.length / 4) * 4, "=");
  return decodeURIComponent(escape(atob(padded)));
}

describe("mediaUrl", () => {
  it("previewUrl targets the correct monitor index route", () => {
    expect(previewUrl(0)).toBe("http://watcher.localhost/preview/m0");
    expect(previewUrl(3)).toBe("http://watcher.localhost/preview/m3");
  });

  it("clipUrl base64url-encodes the path with no padding and no unsafe chars", () => {
    const url = clipUrl(String.raw`C:\WatcherData\clips\2026-07-06_event.mp4`);
    expect(url).toMatch(/^http:\/\/watcher\.localhost\/clip\/[A-Za-z0-9_-]+$/);
    const encoded = url.split("/clip/")[1];
    expect(decodeUrlSafeBase64NoPad(encoded)).toBe(String.raw`C:\WatcherData\clips\2026-07-06_event.mp4`);
  });

  it("clipUrl round-trips UNC paths and unicode", () => {
    const path = String.raw`\\SIG-SLC-Storage\Storage1\Operator-28\clip ñ.mp4`;
    const encoded = clipUrl(path).split("/clip/")[1];
    expect(decodeUrlSafeBase64NoPad(encoded)).toBe(path);
  });
});
