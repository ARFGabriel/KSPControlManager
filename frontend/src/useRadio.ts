import { useCallback, useEffect, useRef, useState } from "react";

export type Persona = "ground" | "crew";

export interface RadioStatus {
  provider: string;
  model: string;
  available: boolean;
  commands: string[];
  irreversible: string[];
}

export interface Entry {
  key: string;
  kind: "message" | "command" | "error";
  persona?: string;
  text: string;
  ok?: boolean;
  name?: string;
  ts: number;
}

export interface Confirmation {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  description: string;
}

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${proto}://${host}/ws/radio`;
}

export function useRadio() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [status, setStatus] = useState<RadioStatus | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [waiting, setWaiting] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const counter = useRef(0);

  const push = useCallback((entry: Omit<Entry, "key">) => {
    counter.current += 1;
    setEntries((prev) => [...prev.slice(-99), { ...entry, key: `e${counter.current}` }]);
  }, []);

  useEffect(() => {
    let closed = false;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(wsUrl());
      socketRef.current = socket;

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "status":
            setStatus(data);
            break;
          case "message":
            // Une réponse arrivée : la radio n'est plus en attente.
            if (data.persona !== "pilote") setWaiting(false);
            push({ kind: "message", persona: data.persona, text: data.text, ts: data.ts });
            break;
          case "command":
            push({
              kind: "command",
              name: data.name,
              text: data.result,
              ok: data.ok,
              ts: data.ts,
            });
            break;
          case "confirmation":
            setWaiting(false);
            setConfirmation(data);
            break;
          case "error":
            setWaiting(false);
            push({ kind: "error", text: data.text, ts: data.ts });
            break;
          case "reset":
            setEntries([]);
            break;
        }
      };

      socket.onclose = () => {
        if (closed) return;
        timer = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      socketRef.current?.close();
    };
  }, [push]);

  const send = useCallback((persona: Persona, text: string) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    setWaiting(true);
    socket.send(JSON.stringify({ type: "send", persona, text }));
  }, []);

  const respond = useCallback((id: string, approved: boolean) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    setConfirmation(null);
    setWaiting(true);
    socket.send(JSON.stringify({ type: "confirm", id, approved }));
  }, []);

  const reset = useCallback(() => {
    socketRef.current?.send(JSON.stringify({ type: "reset" }));
  }, []);

  return { entries, status, confirmation, waiting, send, respond, reset };
}
