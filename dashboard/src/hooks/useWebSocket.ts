import { useEffect, useState, useRef, useCallback } from "react";

interface WebSocketHookProps {
  url: string;
  onMessage?: (data: any) => void;
  enabled?: boolean;
}

export const useWebSocket = ({ url, onMessage, enabled = false }: WebSocketHookProps) => {
  const [status, setStatus] = useState<"connecting" | "open" | "closed" | "error">("closed");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);

  const connect = useCallback(() => {
    if (!enabled) return;

    try {
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("open");
        console.log("WebSocket connected to", url);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (onMessage) {
            onMessage(data);
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onclose = () => {
        setStatus("closed");
        // Auto reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.onerror = (err) => {
        setStatus("error");
        console.error("WebSocket error:", err);
      };
    } catch (error) {
      setStatus("error");
      console.error("WebSocket initialization failed:", error);
    }
  }, [url, onMessage, enabled]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.onclose = null; // Prevent reconnect loop
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("closed");
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);

  const send = useCallback((message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof message === "string" ? message : JSON.stringify(message));
    } else {
      console.warn("WebSocket not open. Message not sent:", message);
    }
  }, []);

  return { status, send };
};
