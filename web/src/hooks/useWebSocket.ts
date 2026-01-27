import { useEffect, useRef, useState, useCallback } from 'react';

interface UseWebSocketOptions {
  onMessage?: (data: any) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;
  maxRetries?: number;
}

export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const urlRef = useRef(url);
  
  // Store callbacks in refs to avoid reconnection on callback changes
  const optionsRef = useRef(options);
  optionsRef.current = options;
  
  const {
    reconnectInterval = 3000,
    maxRetries = 5,
  } = options;

  // Update URL ref
  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  const connect = useCallback(() => {
    const currentUrl = urlRef.current;
    // Don't connect if URL is null
    if (!currentUrl) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const ws = new WebSocket(currentUrl);

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
      optionsRef.current.onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
        optionsRef.current.onMessage?.(data);
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      optionsRef.current.onClose?.();

      // Reconnect only if URL still exists
      if (urlRef.current && retriesRef.current < maxRetries) {
        retriesRef.current++;
        setTimeout(connect, reconnectInterval);
      }
    };

    ws.onerror = (error) => {
      optionsRef.current.onError?.(error);
    };

    wsRef.current = ws;
  }, [reconnectInterval, maxRetries]);

  const disconnect = useCallback(() => {
    retriesRef.current = maxRetries; // Prevent reconnect
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [maxRetries]);

  const sendMessage = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // Connect/disconnect based on URL
  useEffect(() => {
    if (url) {
      connect();
    } else {
      disconnect();
    }
    
    return () => {
      disconnect();
    };
  }, [url, connect, disconnect]);

  return { isConnected, lastMessage, sendMessage, disconnect, reconnect: connect };
}
