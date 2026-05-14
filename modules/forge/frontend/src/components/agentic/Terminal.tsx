import React, { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { Box } from '@mui/material';
import { useIDEStore } from '../../store/useIDEStore';

let terminalIdCounter = 0;

function createTerminalId(): string {
  terminalIdCounter += 1;
  return `forge-${terminalIdCounter}`;
}

const Terminal: React.FC = () => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermref = useRef<XTerm | null>(null);
  const [terminalId] = useState(createTerminalId);
  const observingRef = useRef(false);
  const { adapter, isAgentObserving, appendTerminalTranscript } = useIDEStore();
  const [startupError, setStartupError] = useState<string | null>(null);

  useEffect(() => {
    observingRef.current = isAgentObserving;
  }, [isAgentObserving]);

  useEffect(() => {
    if (!terminalRef.current) return;

    let term: XTerm | null = null;
    let cancelled = false;
    let unlisten: (() => void) | null = null;
    let resizeFrame: number | null = null;

    void Promise.resolve().then(() => {
      if (!cancelled) setStartupError(null);
    });

    try {
      // Initialize xterm.js
      term = new XTerm({
        theme: {
          background: '#0f172a', // Matches Slate 900
          foreground: '#f8fafc',
          cursor: '#4f46e5',
          selectionBackground: 'rgba(79, 70, 229, 0.3)',
        },
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        fontSize: 13,
        cursorBlink: true,
        allowProposedApi: true
      });

      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);

      term.open(terminalRef.current);

      xtermref.current = term;

      const fitSafely = () => {
        if (cancelled || !term || !terminalRef.current) return;
        if (terminalRef.current.clientWidth === 0 || terminalRef.current.clientHeight === 0) return;
        try {
          fitAddon.fit();
          if (adapter) {
            adapter.resizeTerminal(terminalId, term.cols, term.rows).catch((err) => {
              const message = `Terminal resize failed: ${(err as Error).message}`;
              setStartupError(message);
              console.error(message, err);
            });
          }
        } catch (err) {
          console.error('Terminal fit failed:', err);
        }
      };

      resizeFrame = window.requestAnimationFrame(fitSafely);

      // Connect to adapter if available
      if (adapter) {
        adapter
          .createTerminal(
            terminalId,
            (data) => {
              term?.write(data);
              if (observingRef.current) appendTerminalTranscript(data);
            },
            (payload) => {
              const message = `Terminal exited: ${JSON.stringify(payload)}`;
              if (!cancelled) {
                setStartupError(message);
                term?.writeln(`\r\n${message}`);
              }
            },
          )
          .then((dispose) => {
            if (cancelled) {
              dispose();
              return;
            }
            unlisten = dispose;
          })
          .catch((err) => {
            const message = `Terminal failed to start: ${(err as Error).message}`;
            console.error(message, err);
            if (!cancelled) setStartupError(message);
            term?.writeln(`\r\n${message}`);
          });

        term.onData((data) => {
          adapter.writeToTerminal(terminalId, data).catch((err) => {
            console.error('Terminal write failed:', err);
          });
        });
      } else {
        term.writeln('\x1b[1;34mALOSForge\x1b[0m Shell');
        term.writeln('No environment adapter connected. Running in demo mode.');
        term.write('\r\n$ ');
      }

      const handleResize = () => {
        if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
        resizeFrame = window.requestAnimationFrame(fitSafely);
      };

      window.addEventListener('resize', handleResize);

      return () => {
        cancelled = true;
        window.removeEventListener('resize', handleResize);
        if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
        unlisten?.();
        term?.dispose();
      };
    } catch (err) {
      const message = `Terminal render failed: ${(err as Error).message}`;
      console.error(message, err);
      void Promise.resolve().then(() => {
        if (!cancelled) setStartupError(message);
      });
      term?.dispose();
    }

    return () => {
      cancelled = true;
      if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
      unlisten?.();
      term?.dispose();
    };
  }, [adapter, appendTerminalTranscript, terminalId]);

  return (
    <Box sx={{ width: '100%', height: '100%', position: 'relative' }}>
      <Box 
        ref={terminalRef} 
        sx={{ 
          width: '100%', 
          height: '100%',
          '& .xterm': { p: 1 }
        }} 
      />
      {startupError && (
        <Box
          sx={{
            position: 'absolute',
            right: 8,
            bottom: 8,
            maxWidth: 520,
            border: '1px solid #7f1d1d',
            bgcolor: 'rgba(127, 29, 29, 0.24)',
            color: '#fecaca',
            fontSize: '0.75rem',
            p: 1,
            borderRadius: '6px',
          }}
        >
          {startupError}
        </Box>
      )}
    </Box>
  );
};

export default Terminal;
