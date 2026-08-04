import { useEffect, useRef, useState } from "react";
import type { Telemetry } from "./types";

/** Adresse du flux : en developpement le dashboard tourne sur le port 5173 de
 *  Vite alors que le backend ecoute sur 8000 ; une fois compile, les deux sont
 *  servis par la meme origine. */
function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${proto}://${host}/ws/telemetry`;
}

export interface Link {
  telemetry: Telemetry | null;
  /** Etat de la liaison backend (distinct de la liaison KSP). */
  online: boolean;
}

export function useTelemetry(): Link {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [online, setOnline] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  useEffect(() => {
    let closed = false;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(wsUrl());
      socketRef.current = socket;

      socket.onopen = () => {
        setOnline(true);
        retryRef.current = 0;
      };

      socket.onmessage = (event) => {
        try {
          setTelemetry(JSON.parse(event.data) as Telemetry);
        } catch {
          /* trame illisible : on ignore et on attend la suivante */
        }
      };

      socket.onclose = () => {
        setOnline(false);
        if (closed) return;
        // Reconnexion avec un delai croissant, plafonne a 5 s : si le backend
        // redemarre, le dashboard se rebranche tout seul.
        retryRef.current = Math.min(retryRef.current + 1, 10);
        const delay = Math.min(250 * retryRef.current, 5000);
        timer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      socketRef.current?.close();
    };
  }, []);

  return { telemetry, online };
}
