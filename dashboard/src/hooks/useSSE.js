import { useEffect, useRef, useCallback, useState } from "react";

const HUB_URL = import.meta.env.VITE_HUB_URL || "http://localhost:8080";

export function useSSE(onEvent) {
  const [connected, setConnected] = useState(false);
  const esRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(`${HUB_URL}/events`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      es.close();
      // Reconnect after 3s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    // EventSource handles auto-reconnection, but we need to re-register handlers
    // after each reconnect
    const events = [
      "message_sent", "task_transition", "task_created", "task_claimed",
      "task_assigned", "task_unassigned", "agent_registered", "agent_unregistered",
      "agent_paused", "agent_resumed", "agent_revoked", "agent_recovered",
      "checkpoint_submitted", "agent_capabilities_changed", "agent_autonomy_changed",
      "global_autonomy_changed", "project_created", "project_deleted",
      "agent_joined_project", "file_uploaded",
    ];

    events.forEach((type) => {
      es.addEventListener(type, (e) => {
        try {
          const data = JSON.parse(e.data);
          onEvent({ type, data });
        } catch {
          onEvent({ type, data: e.data });
        }
      });
    });
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (esRef.current) esRef.current.close();
    };
  }, [connect]);

  return { connected };
}
