import { Html5Qrcode } from "html5-qrcode";
import { useEffect, useRef } from "react";

const SCANNER_ELEMENT_ID = "qr-reader";
// Client-side throttle so holding the same code in frame doesn't fire
// dozens of decodes a second — separate from the server's duplicate-scan
// window (§9), which is about two genuinely separate scans.
const RESCAN_THROTTLE_MS = 2000;

interface Props {
  onDecode: (text: string) => void;
  active: boolean;
}

export function QrScanner({ onDecode, active }: Props) {
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const lastDecodeRef = useRef<{ text: string; at: number } | null>(null);
  const onDecodeRef = useRef(onDecode);
  onDecodeRef.current = onDecode;

  useEffect(() => {
    if (!active) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, { verbose: false });
    scannerRef.current = scanner;
    let cancelled = false;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        (decodedText) => {
          const last = lastDecodeRef.current;
          const now = Date.now();
          if (last && last.text === decodedText && now - last.at < RESCAN_THROTTLE_MS) {
            return;
          }
          lastDecodeRef.current = { text: decodedText, at: now };
          onDecodeRef.current(decodedText);
        },
        () => {
          // Per-frame decode failures are expected (no code in view) — ignored.
        }
      )
      .catch((err) => {
        if (!cancelled) {
          console.error("Camera start failed", err);
        }
      });

    return () => {
      cancelled = true;
      scanner
        .stop()
        .then(() => scanner.clear())
        .catch(() => {
          /* already stopped */
        });
      scannerRef.current = null;
    };
  }, [active]);

  return <div id={SCANNER_ELEMENT_ID} className="qr-reader" />;
}
